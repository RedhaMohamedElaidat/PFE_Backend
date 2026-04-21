from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Q, Prefetch

# ❌ Supprimez cette ligne
# from Backend import publication

from coAuthor.models import CoAuthor
from coAuthor.serializers import (
    CoAuthorSerializer, 
    CoAuthorCreateSerializer, 
    CoAuthorBulkSerializer,
    CoAuthorUpdateSerializer,
    CoAuthorCollaborationSerializer
)


class CoAuthorViewSet(viewsets.ModelViewSet):
    queryset = CoAuthor.objects.select_related(
        'linked_user',
        'publication'
    ).prefetch_related(
        'publication__journal'
    )

    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]

    filterset_fields = ['publication', 'author_orcid', 'contribution_type', 'author_order']
    ordering_fields = ['author_order', 'publication__publication_year']
    ordering = ['publication__publication_year', 'author_order']

    def get_serializer_class(self):
        if self.action == 'create':
            return CoAuthorCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return CoAuthorUpdateSerializer
        elif self.action == 'bulk_add':
            return CoAuthorBulkSerializer
        elif self.action == 'collaborations':
            return CoAuthorCollaborationSerializer
        return CoAuthorSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'bulk_add']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    # ── Bulk Add avec support de duplication ───────────────────────────────────

    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def bulk_add(self, request):
        """
        Ajout en masse avec support de duplication (même auteur, ordres différents)
        
        Format:
        {
            publication_id: 1,
            authors: [
                {
                    author_name: "John Doe",
                    author_orcid: "0000-0001",
                    openalex_id: "A123",
                    contribution_type: 1,
                    author_order: 1,
                    affiliation_at_time: "CERIST"
                },
                {
                    author_name: "John Doe",
                    author_orcid: "0000-0001",
                    contribution_type: 4,
                    author_order: 4,
                    affiliation_at_time: "CERIST"
                }
            ]
        }
        """
        from publication.models import Publication  # Import ici pour éviter les imports circulaires
        
        serializer = CoAuthorBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        publication_id = serializer.validated_data['publication_id']
        authors = serializer.validated_data['authors']
        
        # Récupérer la publication
        try:
            publication = Publication.objects.get(pk=publication_id)
        except Publication.DoesNotExist:
            return Response(
                {'error': 'Publication introuvable.'},
                status=status.HTTP_404_NOT_FOUND
            )

        created = []
        errors = []

        for author_data in authors:
            try:
                # Créer l'entrée
                ca = CoAuthor.objects.create(
                    publication=publication,
                    author_name=author_data.get('author_name'),
                    author_orcid=author_data.get('author_orcid'),
                    openalex_id=author_data.get('openalex_id'),
                    contribution_type=author_data.get('contribution_type', 5),
                    author_order=author_data.get('author_order', 1),
                    affiliation_at_time=author_data.get('affiliation_at_time', ''),
                    linked_user=author_data.get('linked_user'),
                )
                created.append(ca)
            except Exception as e:
                errors.append({
                    'author': author_data.get('author_name', 'Unknown'),
                    'error': str(e)
                })

        response_data = {
            'created': CoAuthorSerializer(created, many=True).data,
            'created_count': len(created),
            'errors': errors
        }

        status_code = status.HTTP_201_CREATED if created else status.HTTP_400_BAD_REQUEST
        return Response(response_data, status=status_code)

    # ── By Publication avec support de duplication ─────────────────────────────

    @action(detail=False, methods=['get'])
    def by_publication(self, request):
        """
        Récupère tous les co-auteurs d'une publication
        GET /api/coauthors/by_publication/?id=123
        
        Retourne toutes les entrées, y compris les doublons (même auteur, ordres différents)
        """
        pub_id = request.query_params.get('id')

        if not pub_id:
            return Response(
                {'error': 'Paramètre id requis.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        qs = CoAuthor.objects.filter(
            publication_id=pub_id
        ).select_related('linked_user', 'publication').order_by('author_order')

        # Option de regroupement par auteur
        group_by_author = request.query_params.get('group', '').lower() == 'true'
        
        if group_by_author:
            # Regrouper par auteur et collecter les ordres
            authors_dict = {}
            for ca in qs:
                key = ca.author_orcid or ca.openalex_id or ca.author_name
                if key not in authors_dict:
                    authors_dict[key] = {
                        'author_name': ca.author_name,
                        'author_orcid': ca.author_orcid,
                        'openalex_id': ca.openalex_id,
                        'linked_user': ca.linked_user,
                        'roles': []
                    }
                authors_dict[key]['roles'].append({
                    'order': ca.author_order,
                    'contribution_type': ca.contribution_type,
                    'contribution_display': ca.get_contribution_type_display(),
                    'affiliation': ca.affiliation_at_time
                })
            
            return Response(list(authors_dict.values()))

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    # ── By Author avec support de duplication ─────────────────────────────

    @action(detail=False, methods=['get'])
    def by_author(self, request):
        """
        Récupère toutes les publications d'un auteur
        GET /api/coauthors/by_author/?orcid=XXX
        GET /api/coauthors/by_author/?name=John%20Doe
        """
        orcid = request.query_params.get('orcid')
        name = request.query_params.get('name')
        
        if not orcid and not name:
            return Response(
                {'error': 'Paramètre orcid ou name requis.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        qs = CoAuthor.objects.select_related('publication', 'linked_user')
        
        if orcid:
            qs = qs.filter(author_orcid=orcid)
        elif name:
            qs = qs.filter(author_name__icontains=name)
        
        qs = qs.order_by('-publication__publication_year', 'author_order')
        
        # Option pour inclure les statistiques
        include_stats = request.query_params.get('stats', '').lower() == 'true'
        
        if include_stats:
            # Compter les publications par type de contribution
            stats = {
                'total_publications': qs.count(),
                'by_contribution': {},
                'by_year': {}
            }
            
            for ca in qs:
                # Par type de contribution
                contrib_type = ca.get_contribution_type_display()
                stats['by_contribution'][contrib_type] = stats['by_contribution'].get(contrib_type, 0) + 1
                
                # Par année
                year = ca.publication.publication_year
                if year:
                    stats['by_year'][year] = stats['by_year'].get(year, 0) + 1
            
            response_data = {
                'coauthors': CoAuthorSerializer(qs, many=True).data,
                'stats': stats
            }
            return Response(response_data)
        
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    # ── My Publications (avec mes rôles) ─────────────────────────────

    @action(detail=False, methods=['get'], url_path='my-publications')
    def my_publications(self, request):
        """
        Récupère mes publications avec mes rôles
        GET /api/coauthors/my-publications/
        Option: ?include_all_authors=true  # Pour voir tous les co-auteurs
        """
        user = request.user
        include_all_authors = request.query_params.get('include_all_authors', '').lower() == 'true'
        
        # Récupérer toutes mes entrées CoAuthor
        my_entries = CoAuthor.objects.filter(
            linked_user=user
        ).select_related('publication').order_by('-publication__publication_year', 'author_order')
        
        # Structurer par publication
        publications_dict = {}
        for entry in my_entries:
            pub = entry.publication
            if pub.id not in publications_dict:
                # Récupérer TOUS les co-auteurs de cette publication si demandé
                if include_all_authors:
                    all_authors = CoAuthor.objects.filter(
                        publication=pub
                    ).select_related('linked_user').order_by('author_order')
                    
                    publications_dict[pub.id] = {
                        'publication_id': pub.id,
                        'title': pub.title,
                        'year': pub.publication_year,
                        'doi': pub.doi,
                        'citations': pub.citation_count,
                        'journal': pub.journal.name if pub.journal else None,
                        'my_roles': [],
                        'all_authors': []
                    }
                    
                    # Ajouter tous les auteurs
                    for author in all_authors:
                        publications_dict[pub.id]['all_authors'].append({
                            'name': author.author_name,
                            'order': author.author_order,
                            'orcid': author.author_orcid,
                            'contribution_type': author.contribution_type,
                            'contribution_display': author.get_contribution_type_display(),
                            'has_account': author.linked_user is not None,
                            'is_me': author.linked_user == user
                        })
                else:
                    publications_dict[pub.id] = {
                        'publication_id': pub.id,
                        'title': pub.title,
                        'year': pub.publication_year,
                        'doi': pub.doi,
                        'citations': pub.citation_count,
                        'journal': pub.journal.name if pub.journal else None,
                        'my_roles': []
                    }
            
            publications_dict[pub.id]['my_roles'].append({
                'order': entry.author_order,
                'contribution_type': entry.contribution_type,
                'contribution_display': entry.get_contribution_type_display(),
                'affiliation': entry.affiliation_at_time
            })
        
        return Response(list(publications_dict.values()))

    # ── My Coauthors (avec nombre de collaborations) ──────────────────────

    @action(detail=False, methods=['get'], url_path='my-coauthors')
    def my_coauthors(self, request):
        """
        Récupère tous mes co-auteurs avec le nombre de collaborations
        GET /api/coauthors/my-coauthors/
        """
        user = request.user

        # Mes publications
        my_publications = CoAuthor.objects.filter(
            linked_user=user
        ).values_list('publication_id', flat=True)

        # Tous les co-auteurs sur mes publications (sauf moi)
        coauthors = CoAuthor.objects.filter(
            publication_id__in=my_publications
        ).exclude(
            linked_user=user
        ).select_related('linked_user')
        
        # Agréger par auteur
        coauthors_dict = {}
        for ca in coauthors:
            key = ca.author_orcid or ca.openalex_id or ca.author_name
            
            if key not in coauthors_dict:
                coauthors_dict[key] = {
                    'author_name': ca.author_name,
                    'author_orcid': ca.author_orcid,
                    'openalex_id': ca.openalex_id,
                    'linked_user': ca.linked_user,
                    'collaborations': 0,
                    'publications': [],
                    'roles_summary': {
                        'first_author': 0,
                        'corresponding': 0,
                        'other': 0
                    }
                }
            
            coauthors_dict[key]['collaborations'] += 1
            coauthors_dict[key]['publications'].append(ca.publication_id)
            
            # Résumé des rôles
            if ca.contribution_type == 1:
                coauthors_dict[key]['roles_summary']['first_author'] += 1
            elif ca.contribution_type == 4:
                coauthors_dict[key]['roles_summary']['corresponding'] += 1
            else:
                coauthors_dict[key]['roles_summary']['other'] += 1
        
        # Trier par nombre de collaborations décroissant
        sorted_coauthors = sorted(
            coauthors_dict.values(),
            key=lambda x: x['collaborations'],
            reverse=True
        )
        
        return Response(sorted_coauthors)

    # ── My Collaborations (détaillé) ────────────────────────────────

    @action(detail=False, methods=['get'], url_path='my-collaborations')
    def my_collaborations(self, request):
        """
        Récupère toutes mes collaborations avec détails
        GET /api/coauthors/my-collaborations/
        Option: ?group_by=author
        """
        user = request.user
        group_by = request.query_params.get('group_by', '').lower()

        my_publications = CoAuthor.objects.filter(
            linked_user=user
        ).values_list('publication_id', flat=True)

        collaborations = CoAuthor.objects.filter(
            publication_id__in=my_publications
        ).select_related('linked_user', 'publication', 'publication__journal') \
         .order_by('-publication__publication_year', 'author_order')
        
        if group_by == 'author':
            # Grouper par auteur
            author_dict = {}
            for ca in collaborations:
                if ca.linked_user:
                    key = ca.linked_user.id
                else:
                    key = ca.author_orcid or ca.author_name
                
                if key not in author_dict:
                    author_dict[key] = {
                        'author_name': ca.author_name,
                        'author_orcid': ca.author_orcid,
                        'linked_user': ca.linked_user,
                        'collaborations': [],
                        'total_collaborations': 0
                    }
                
                author_dict[key]['collaborations'].append({
                    'publication_id': ca.publication.id,
                    'publication_title': ca.publication.title,
                    'publication_year': ca.publication.publication_year,
                    'author_order': ca.author_order,
                    'contribution_type': ca.contribution_type,
                    'contribution_display': ca.get_contribution_type_display(),
                })
                author_dict[key]['total_collaborations'] += 1
            
            return Response(list(author_dict.values()))
        
        serializer = CoAuthorCollaborationSerializer(collaborations, many=True)
        return Response(serializer.data)

    # ── Author Network (graph) ────────────────────────────────

    @action(detail=False, methods=['get'], url_path='author-network')
    def author_network(self, request):
        """
        Construit un graphe de collaboration
        GET /api/coauthors/author-network/?orcid=XXX
        """
        orcid = request.query_params.get('orcid')
        
        if not orcid:
            return Response(
                {'error': 'Paramètre orcid requis.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Publications de l'auteur
        publications = CoAuthor.objects.filter(
            author_orcid=orcid
        ).values_list('publication_id', flat=True)
        
        # Tous les co-auteurs sur ces publications
        coauthors = CoAuthor.objects.filter(
            publication_id__in=publications
        ).exclude(
            author_orcid=orcid
        ).select_related('linked_user')
        
        # Construire le graphe
        nodes = {}
        edges = []
        
        for ca in coauthors:
            # Ajouter le nœud
            node_key = ca.author_orcid or ca.author_name
            if node_key not in nodes:
                nodes[node_key] = {
                    'id': node_key,
                    'name': ca.author_name,
                    'orcid': ca.author_orcid,
                    'linked_user': ca.linked_user,
                    'publications': set()
                }
            nodes[node_key]['publications'].add(ca.publication_id)
        
        # Créer les arêtes (collaborations)
        for node_key, node_data in nodes.items():
            for other_key, other_data in nodes.items():
                if node_key < other_key:  # Éviter les doublons
                    common_pubs = node_data['publications'] & other_data['publications']
                    if common_pubs:
                        edges.append({
                            'source': node_key,
                            'target': other_key,
                            'weight': len(common_pubs),
                            'publications': list(common_pubs)
                        })
        
        return Response({
            'nodes': [{
                'id': n['id'],
                'name': n['name'],
                'orcid': n['orcid'],
                'publication_count': len(n['publications'])
            } for n in nodes.values()],
            'edges': edges
        })

    # ── Fix Duplicate Orders ────────────────────────────────

    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser], url_path='fix-duplicates')
    def fix_duplicates(self, request):
        """
        Corrige les doublons potentiels (même publication, même auteur, même ordre)
        """
        # Trouver les doublons
        duplicates = CoAuthor.objects.values(
            'publication_id', 'author_orcid', 'author_order'
        ).annotate(
            count=Count('id')
        ).filter(count__gt=1)
        
        fixed_count = 0
        
        for dup in duplicates:
            entries = CoAuthor.objects.filter(
                publication_id=dup['publication_id'],
                author_orcid=dup['author_orcid'],
                author_order=dup['author_order']
            ).order_by('id')
            
            # Garder la première, supprimer les autres
            to_keep = entries.first()
            to_delete = entries.exclude(id=to_keep.id)
            deleted_count = to_delete.delete()[0]
            fixed_count += deleted_count
            
            print(f"Fixed: Publication {dup['publication_id']}, "
                  f"Author {dup['author_orcid']}, Order {dup['author_order']}: "
                  f"Deleted {deleted_count} duplicates")
        
        return Response({
            'fixed': fixed_count,
            'message': f'{fixed_count} entrées dupliquées supprimées'
        })