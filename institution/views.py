from django.utils import timezone  # ← AJOUTEZ CETTE LIGNE EN HAUT DU FICHIER
from rest_framework import viewsets, filters
from rest_framework import permissions
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from users.models import InstitutionDirector
from institution.models import Country, Wilaya, Ville, Institution
from institution.serializers import (
    CountrySerializer, WilayaSerializer,
    VilleSerializer, InstitutionSerializer, InstitutionDetailSerializer
)


# ─────────────────────────────────────────
# COUNTRY
# ─────────────────────────────────────────
class CountryViewSet(viewsets.ModelViewSet):
    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering = ['name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]


# ─────────────────────────────────────────
# WILAYA
# ─────────────────────────────────────────
class WilayaViewSet(viewsets.ModelViewSet):
    queryset = Wilaya.objects.select_related('country')
    serializer_class = WilayaSerializer
    permission_classes = [IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['country']  # ✅ OK
    search_fields = ['name']
    ordering = ['name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            # Allow admin OR institution director
            return [IsAdminUser() | IsInstitutionDirectorForInstitution()]
        return [IsAuthenticated()]


# ─────────────────────────────────────────
# VILLE (corrigé)
# ─────────────────────────────────────────
class VilleViewSet(viewsets.ModelViewSet):
    queryset = Ville.objects.select_related('wilaya')  # ✅ corrigé
    serializer_class = VilleSerializer
    permission_classes = [IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['wilaya']  # ✅ corrigé
    search_fields = ['name']
    ordering = ['name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

class IsInstitutionDirectorForInstitution(permissions.BasePermission):
    """
    Custom permission to allow institution directors to edit their own institution
    """
    
    def has_object_permission(self, request, view, obj):
        # Read-only permissions for any authenticated user
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions only for admin users OR the institution's director
        if request.user and request.user.is_staff:
            return True
        
        # Check if the user is the director of this institution
        try:
            director = InstitutionDirector.objects.get(user=request.user)
            return director.institution == obj
        except InstitutionDirector.DoesNotExist:
            return False
# ─────────────────────────────────────────
# INSTITUTION (corrigé)
# ─────────────────────────────────────────
class InstitutionViewSet(viewsets.ModelViewSet):
    queryset = Institution.objects.select_related('ville__wilaya')  # ✅ corrigé
    permission_classes = [IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['type', 'ville']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'type']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return InstitutionDetailSerializer
        return InstitutionSerializer

    def get_permissions(self):
        """
        Returns the permission classes based on the action.
        - List and retrieve: just need to be authenticated
        - Create, update, delete: need to be admin OR institution director
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            # Allow admin users OR institution directors
            return [IsInstitutionDirectorForInstitution()]
        return [IsAuthenticated()]

    # ─────────────────────────────────────────
    # STATS
    # ─────────────────────────────────────────
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        institution = self.get_object()
        return Response({
            'total_publications': institution.get_total_publications(),
            'average_h_index': institution.get_average_h_index(),
            'top_researchers': [
                {
                    'id': u.user_id,
                    'name': u.get_full_name(),
                    'h_index': getattr(getattr(u, 'researcher_profile', None), 'h_index', 0),
                }
                for u in institution.get_top_researchers(limit=10)
            ],
        })

    # ─────────────────────────────────────────
    # LABS
    # ─────────────────────────────────────────
    @action(detail=True, methods=['get'])
    def laboratories(self, request, pk=None):
        from laboratory.models import Laboratory
        from laboratory.serializers import LaboratorySerializer

        institution = self.get_object()
        labs = Laboratory.objects.filter(institution=institution)

        return Response(LaboratorySerializer(labs, many=True).data)

    @action(detail=True, methods=['get'], url_path='available-users')
    def available_users(self, request, pk=None):
        """
        GET /api/institutions/{id}/available-users/
        Retourne les utilisateurs disponibles qui peuvent être nommés chef de laboratoire
        (utilisateurs qui ne sont ni LabManager ni TeamLeader)
        """
        from users.models import User, LabManager, TeamLeader
        
        institution = self.get_object()
        
        # Récupérer tous les IDs des utilisateurs qui sont déjà LabManager
        lab_manager_ids = LabManager.objects.values_list('user_id', flat=True)
        
        # Récupérer tous les IDs des utilisateurs qui sont déjà TeamLeader
        team_leader_ids = TeamLeader.objects.values_list('user_id', flat=True)
        
        # Récupérer les utilisateurs qui ne sont ni LabManager ni TeamLeader
        # et qui sont des chercheurs (ont un profil researcher)
        available_users = User.objects.filter(
            researcher_profile__isnull=False,  # A un profil chercheur
            is_active=True
        ).exclude(
            user_id__in=lab_manager_ids
        ).exclude(
            user_id__in=team_leader_ids
        ).distinct()
        
        # Sérialiser les données
        users_data = []
        for user in available_users:
            users_data.append({
                'id': user.user_id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'full_name': user.get_full_name() or user.username,
                'h_index': getattr(user.researcher_profile, 'h_index', 0) if hasattr(user, 'researcher_profile') else 0,
                'research_field': getattr(user.researcher_profile, 'research_field', 'Non spécifié') if hasattr(user, 'researcher_profile') else 'Non spécifié',
            })
        
        return Response(users_data)


    @action(detail=True, methods=['post'], url_path='create-laboratory')
    def create_laboratory(self, request, pk=None):
        """
        POST /api/institutions/{id}/create-laboratory/
        Crée un nouveau laboratoire dans l'institution
        Body: {
            "name": "Nom du laboratoire",
            "description": "Description",
            "website": "https://...",
            "manager_id": 123 (optionnel)
        }
        """
        from laboratory.models import Laboratory
        from users.models import LabManager, User
        from django.utils import timezone
        
        institution = self.get_object()
        
        name = request.data.get('name')
        description = request.data.get('description', '')
        website = request.data.get('website', '')
        manager_id = request.data.get('manager_id')
        
        if not name:
            return Response({'error': 'Le nom du laboratoire est requis'}, status=400)
        
        # Vérifier si un laboratoire avec ce nom existe déjà dans l'institution
        if Laboratory.objects.filter(name=name, institution=institution).exists():
            return Response({'error': 'Un laboratoire avec ce nom existe déjà'}, status=400)
        
        # Créer le laboratoire
        laboratory = Laboratory.objects.create(
            name=name,
            description=description,
            website=website,
            institution=institution
        )
        
        # Assigner un manager si spécifié
        manager_assigned = None
        if manager_id:
            try:
                user = User.objects.get(user_id=manager_id)
                # Vérifier que l'utilisateur n'est pas déjà LabManager
                if not LabManager.objects.filter(user=user).exists():
                    LabManager.objects.create(
                        user=user,
                        laboratory=laboratory,
                        start_date=timezone.now().date()
                    )
                    manager_assigned = user.get_full_name() or user.username
            except User.DoesNotExist:
                pass
        
        return Response({
            'success': True,
            'message': f'Laboratoire "{name}" créé avec succès',
            'laboratory': {
                'id': laboratory.ID,
                'name': laboratory.name,
                'description': laboratory.description,
                'website': laboratory.website,
                'manager': manager_assigned,
            }
        }, status=201)


    @action(detail=True, methods=['put'], url_path='update-laboratory/(?P<lab_id>[^/.]+)')
    def update_laboratory(self, request, pk=None, lab_id=None):
        """
        PUT /api/institutions/{id}/update-laboratory/{lab_id}/
        Met à jour un laboratoire
        """
        from laboratory.models import Laboratory
        from users.models import LabManager, User
        from django.utils import timezone
        
        institution = self.get_object()
        
        try:
            laboratory = Laboratory.objects.get(ID=lab_id, institution=institution)
        except Laboratory.DoesNotExist:
            return Response({'error': 'Laboratoire non trouvé'}, status=404)
        
        name = request.data.get('name')
        description = request.data.get('description')
        website = request.data.get('website')
        manager_id = request.data.get('manager_id')
        
        if name:
            # Vérifier si un autre laboratoire a le même nom
            if Laboratory.objects.filter(name=name, institution=institution).exclude(ID=lab_id).exists():
                return Response({'error': 'Un laboratoire avec ce nom existe déjà'}, status=400)
            laboratory.name = name
        
        if description is not None:
            laboratory.description = description
        
        if website is not None:
            laboratory.website = website
        
        laboratory.save()
        
        # Gérer le changement de manager
        manager_changed = None
        if manager_id:
            try:
                user = User.objects.get(user_id=manager_id)
                
                # Désactiver l'ancien manager
                LabManager.objects.filter(laboratory=laboratory).update(end_date=timezone.now().date())
                
                # Créer le nouveau manager
                LabManager.objects.create(
                    user=user,
                    laboratory=laboratory,
                    start_date=timezone.now().date()
                )
                manager_changed = user.get_full_name() or user.username
            except User.DoesNotExist:
                pass
        
        return Response({
            'success': True,
            'message': f'Laboratoire "{laboratory.name}" mis à jour avec succès',
            'laboratory': {
                'id': laboratory.ID,
                'name': laboratory.name,
                'description': laboratory.description,
                'website': laboratory.website,
                'manager': laboratory.current_manager.get_full_name() if laboratory.current_manager else None,
            }
        })


    @action(detail=True, methods=['delete'], url_path='delete-laboratory/(?P<lab_id>[^/.]+)')
    def delete_laboratory(self, request, pk=None, lab_id=None):
        """
        DELETE /api/institutions/{id}/delete-laboratory/{lab_id}/
        Supprime un laboratoire
        """
        from laboratory.models import Laboratory
        
        institution = self.get_object()
        
        try:
            laboratory = Laboratory.objects.get(ID=lab_id, institution=institution)
            lab_name = laboratory.name
            laboratory.delete()
            
            return Response({
                'success': True,
                'message': f'Laboratoire "{lab_name}" supprimé avec succès'
            })
        except Laboratory.DoesNotExist:
            return Response({'error': 'Laboratoire non trouvé'}, status=404)
# institution/views.py - Version complètement corrigée

    @action(detail=True, methods=['get'], url_path='dashboard')
    def dashboard_data(self, request, pk=None):
        """
        GET /api/institutions/{id}/dashboard/
        Données complètes pour le tableau de bord du directeur d'institution
        """
        from publication.models import Publication
        from users.models import Researcher
        from django.db.models import Sum
        
        institution = self.get_object()
        
        # Récupérer tous les IDs des laboratoires
        lab_ids = list(institution.laboratories.values_list('ID', flat=True))
        
        if not lab_ids:
            return Response({
                'institution': {
                    'id': institution.id,
                    'name': institution.name,
                    'type': institution.type,
                    'type_display': institution.get_type_display(),
                    'description': institution.description,
                    'website': institution.website,
                    'ville': institution.ville.name if institution.ville else None,
                },
                'stats': {
                    'total_laboratories': 0,
                    'total_publications': 0,
                    'total_publications_unique': 0,
                    'total_citations': 0,
                    'total_collaborations': 0,
                    'average_h_index': 0,
                    'total_researchers': 0,
                    'publications_growth': 0,
                },
                'laboratories': [],
                'publications_by_year': [],
                'citations_by_year': [],
                'top_researchers': [],
                'recent_activity': [],
            })
        
        # ✅ Récupérer tous les chercheurs UNIQUES
        researchers = Researcher.objects.filter(
            user__teams__laboratory__in=lab_ids
        ).distinct()
        
        # ✅ Calculer la SOMME des publications individuelles (avec chevauchements)
        total_publications_sum = 0
        total_citations_sum = 0
        for researcher in researchers:
            total_publications_sum += researcher.publications.count()
            total_citations_sum += researcher.publications.aggregate(total=Sum('citation_count'))['total'] or 0
        
        # ✅ Pour les publications UNIQUES (sans chevauchements) - pour les graphiques
        publication_ids = set(
            Publication.objects.filter(
                coauthors__linked_user__teams__laboratory__in=lab_ids,
                is_validated=True
            ).values_list('id', flat=True).distinct()
        )
        publications = Publication.objects.filter(id__in=publication_ids)
        total_publications_unique = len(publication_ids)
        
        # Statistiques globales
        stats = {
            'total_laboratories': institution.laboratories.count(),
            'total_publications': total_publications_sum,  # ← 119 (somme avec chevauchements)
            'total_publications_unique': total_publications_unique,  # ← Publications uniques
            'total_citations': total_citations_sum,
            'total_collaborations': self._get_total_collaborations(institution),
            'average_h_index': round(self._get_average_h_index(institution), 2),
            'total_researchers': researchers.count(),
            'publications_growth': self._calculate_growth(self._get_publications_by_year(institution)),
        }
        
        # Données des laboratoires
        labs_data = []
        for lab in institution.laboratories.all():
            # Chercheurs du laboratoire
            lab_researchers = Researcher.objects.filter(
                user__teams__laboratory=lab
            ).distinct()
            
            # SOMME des publications individuelles des chercheurs du laboratoire
            lab_publications_sum = 0
            lab_citations_sum = 0
            for r in lab_researchers:
                lab_publications_sum += r.publications.count()
                lab_citations_sum += r.publications.aggregate(total=Sum('citation_count'))['total'] or 0
            
            # H-Index moyen
            lab_h_indices = lab_researchers.exclude(h_index__isnull=True).values_list('h_index', flat=True)
            lab_h_index_avg = sum(lab_h_indices) / len(lab_h_indices) if lab_h_indices else 0
            
            labs_data.append({
                'id': lab.ID,
                'name': lab.name,
                'manager': lab.current_manager.get_full_name() if lab.current_manager else 'Non assigné',
                'publications': lab_publications_sum,  # ← Somme des publications individuelles
                'citations': lab_citations_sum,
                'researchers': lab_researchers.count(),
                'teams': lab.teams.count(),
                'h_index_avg': round(lab_h_index_avg, 2),
            })
        
        # Trier par nombre de publications
        labs_data.sort(key=lambda x: x['publications'], reverse=True)
        
        # Publications par année (pour le graphique - utiliser les publications UNIQUES)
        publications_by_year = self._get_publications_by_year(institution)
        citations_by_year = self._get_citations_by_year(institution)
        
        # Top chercheurs
        top_researchers = []
        for researcher in self._get_top_researchers(institution, 10):
            lab_name = None
            if researcher.user.teams.exists():
                lab_name = researcher.user.teams.first().laboratory.name
            
            top_researchers.append({
                'id': researcher.user.user_id,
                'name': researcher.user.get_full_name() or researcher.user.username,
                'h_index': researcher.h_index or 0,
                'research_field': researcher.research_field or 'Non spécifié',
                'laboratory': lab_name,
                'publication_count': researcher.publications.count(),
            })
        
        # Activité récente (utiliser les publications UNIQUES)
        recent_activity = []
        recent_pubs = publications.order_by('-publication_year', '-id')[:10]
        for pub in recent_pubs:
            lab_name = None
            for coauthor in pub.coauthors.all():
                if coauthor.linked_user and coauthor.linked_user.teams.exists():
                    lab_name = coauthor.linked_user.teams.first().laboratory.name
                    break
            
            recent_activity.append({
                'title': pub.title,
                'year': pub.publication_year,
                'citations': pub.citation_count or 0,
                'laboratory': lab_name or 'Non spécifié',
            })
        
        return Response({
            'institution': {
                'id': institution.id,
                'name': institution.name,
                'type': institution.type,
                'type_display': institution.get_type_display(),
                'description': institution.description,
                'website': institution.website,
                'ville': institution.ville.name if institution.ville else None,
            },
            'stats': stats,
            'laboratories': labs_data,
            'publications_by_year': publications_by_year,
            'citations_by_year': citations_by_year,
            'top_researchers': top_researchers,
            'recent_activity': recent_activity,
        })


    def _get_publications_by_year(self, institution):
        """Publications par année (UNIQUES)"""
        from publication.models import Publication
        from collections import defaultdict
        
        lab_ids = institution.laboratories.values_list('ID', flat=True)
        
        if not lab_ids:
            return []
        
        # Récupérer les IDs UNIQUES des publications
        publication_ids = set(
            Publication.objects.filter(
                coauthors__linked_user__teams__laboratory__in=lab_ids,
                is_validated=True
            ).values_list('id', flat=True).distinct()
        )
        
        # Compter par année
        year_counts = defaultdict(int)
        for pub in Publication.objects.filter(id__in=publication_ids):
            year = pub.publication_year or 2024
            year_counts[year] += 1
        
        result = []
        current_year = timezone.now().year
        for year in range(current_year - 5, current_year + 1):
            result.append({
                'year': year,
                'publications': year_counts.get(year, 0)
            })
        
        return result


    def _get_citations_by_year(self, institution):
        """Citations par année (UNIQUES)"""
        from publication.models import Publication
        from collections import defaultdict
        
        lab_ids = institution.laboratories.values_list('ID', flat=True)
        
        if not lab_ids:
            return []
        
        # Récupérer les IDs UNIQUES des publications
        publication_ids = set(
            Publication.objects.filter(
                coauthors__linked_user__teams__laboratory__in=lab_ids,
                is_validated=True
            ).values_list('id', flat=True).distinct()
        )
        
        # Compter les citations par année
        year_citations = defaultdict(int)
        for pub in Publication.objects.filter(id__in=publication_ids):
            year = pub.publication_year or 2024
            year_citations[year] += pub.citation_count or 0
        
        result = []
        current_year = timezone.now().year
        for year in range(current_year - 5, current_year + 1):
            result.append({
                'year': year,
                'citations': year_citations.get(year, 0)
            })
        
        return result

    def _get_average_h_index(self, institution):
        """H-Index moyen des chercheurs"""
        from users.models import Researcher
        
        lab_ids = institution.laboratories.values_list('ID', flat=True)
        
        if not lab_ids:
            return 0
            
        researchers = Researcher.objects.filter(
            user__teams__laboratory__in=lab_ids
        ).distinct()
        
        h_indices = [r.h_index for r in researchers if r.h_index]
        
        if not h_indices:
            return 0
            
        return sum(h_indices) / len(h_indices)

    def _get_top_researchers(self, institution, limit=10):
        """Top chercheurs par H-Index"""
        from users.models import Researcher
        
        lab_ids = institution.laboratories.values_list('ID', flat=True)
        
        if not lab_ids:
            return []
            
        researchers = Researcher.objects.filter(
            user__teams__laboratory__in=lab_ids
        ).distinct().order_by('-h_index')[:limit]
        
        return researchers

    def _calculate_growth(self, publications_by_year):
        """Calcule le taux de croissance sur 3 ans"""
        if len(publications_by_year) < 2:
            return 0
        
        recent = publications_by_year[-3:] if len(publications_by_year) >= 3 else publications_by_year
        if len(recent) < 2:
            return 0
        
        oldest = recent[0]['publications']
        newest = recent[-1]['publications']
        
        if oldest == 0:
            return 100 if newest > 0 else 0
        
        return round(((newest - oldest) / oldest) * 100, 1)
    # Ajoutez cette méthode dans la classe InstitutionViewSet, après les autres méthodes

    def _get_total_collaborations(self, institution):
        """Nombre total de collaborations uniques"""
        from coAuthor.models import CoAuthor
        from users.models import Researcher
        
        lab_ids = institution.laboratories.values_list('ID', flat=True)
        
        if not lab_ids:
            return 0
            
        # Récupérer les IDs uniques des membres des laboratoires
        member_ids = set(
            Researcher.objects.filter(
                user__teams__laboratory__in=lab_ids
            ).values_list('user_id', flat=True).distinct()
        )
        
        if not member_ids:
            return 0
        
        # Récupérer les IDs uniques des publications des membres
        publication_ids = set(
            CoAuthor.objects.filter(
                linked_user_id__in=member_ids
            ).values_list('publication_id', flat=True).distinct()
        )
        
        # Compter les collaborations uniques (co-auteurs externes)
        collaborations = CoAuthor.objects.filter(
            publication_id__in=publication_ids
        ).exclude(
            linked_user_id__in=member_ids
        ).values('author_name', 'author_orcid').distinct().count()
        
        return collaborations
    
    @action(detail=True, methods=['get'], url_path='available-members')
    def available_members(self, request, pk=None):
        """
        GET /api/institutions/{id}/available-members/
        Retourne les chercheurs disponibles pour être MEMBRES d'une équipe
        """
        from users.models import Researcher, TeamLeader, LabManager, User
        
        institution = self.get_object()
        
        # Récupérer tous les IDs des laboratoires de l'institution
        lab_ids = institution.laboratories.values_list('ID', flat=True)
        
        if not lab_ids:
            return Response([])
        
        # ✅ CORRECTION: Récupérer TOUS les chercheurs qui sont dans les laboratoires
        # via leurs équipes OU qui ont une relation directe avec un laboratoire
        all_researchers = Researcher.objects.filter(
            user__teams__laboratory__in=lab_ids  # Chercheurs dans des équipes
        ).distinct()
        
        # Si vous avez des chercheurs qui n'ont pas d'équipe mais sont associés à un laboratoire
        # (par exemple via un champ laboratory dans User), ajoutez cette condition:
        if hasattr(User, 'laboratory'):
            researchers_without_team = Researcher.objects.filter(
                user__laboratory__in=lab_ids,
                user__teams__isnull=True  # Sans équipe
            ).distinct()
            all_researchers = (all_researchers | researchers_without_team).distinct()
        
        print(f"=== AVAILABLE MEMBERS DEBUG ===")
        print(f"Total researchers found: {all_researchers.count()}")
        for r in all_researchers:
            print(f"  - {r.user.get_full_name()} (ID: {r.user.user_id})")
        
        # IDs des exclus (TeamLeader et LabManager)
        team_leader_ids = set(
            TeamLeader.objects.filter(end_date__isnull=True).values_list('user_id', flat=True)
        )
        lab_manager_ids = set(
            LabManager.objects.filter(end_date__isnull=True).values_list('user_id', flat=True)
        )
        
        print(f"Team Leader IDs: {team_leader_ids}")
        print(f"Lab Manager IDs: {lab_manager_ids}")
        
        # Construire la liste des membres disponibles
        available_members = []
        for researcher in all_researchers:
            user = researcher.user
            user_id = user.user_id
            
            # Vérifier si le chercheur est TeamLeader ou LabManager
            is_team_leader = user_id in team_leader_ids
            is_lab_manager = user_id in lab_manager_ids
            
            # Un membre peut être disponible même s'il est déjà dans une équipe
            if not is_team_leader and not is_lab_manager:
                is_in_team = user.teams.exists()
                
                available_members.append({
                    'id': user.user_id,
                    'userId': user.user_id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'full_name': user.get_full_name() or user.username,
                    'fullName': user.get_full_name() or user.username,
                    'h_index': researcher.h_index,
                    'research_field': researcher.research_field or 'Non spécifié',
                    'isInTeam': is_in_team,
                    'status': 'in_team' if is_in_team else 'available',
                })
                print(f"  ✅ {user.get_full_name()} - is_in_team={is_in_team}")
            else:
                print(f"  ❌ Excluded: {user.get_full_name()} (TeamLeader or LabManager)")
        
        print(f"Total available members: {len(available_members)}")
        
        return Response(available_members)


    @action(detail=True, methods=['get'], url_path='available-team-leaders')
    def available_team_leaders(self, request, pk=None):
        """
        GET /api/institutions/{id}/available-team-leaders/
        Retourne les chercheurs disponibles pour être TEAM LEADER
        """
        from users.models import Researcher, TeamLeader, LabManager, User
        
        institution = self.get_object()
        
        # Récupérer tous les IDs des laboratoires de l'institution
        lab_ids = institution.laboratories.values_list('ID', flat=True)
        
        if not lab_ids:
            return Response([])
        
        # ✅ CORRECTION: Récupérer TOUS les chercheurs des laboratoires
        all_researchers = Researcher.objects.filter(
            user__teams__laboratory__in=lab_ids
        ).distinct()
        
        # Inclure aussi les chercheurs sans équipe si le champ laboratory existe
        if hasattr(User, 'laboratory'):
            researchers_without_team = Researcher.objects.filter(
                user__laboratory__in=lab_ids,
                user__teams__isnull=True
            ).distinct()
            all_researchers = (all_researchers | researchers_without_team).distinct()
        
        print(f"=== AVAILABLE TEAM LEADERS DEBUG ===")
        print(f"Total researchers found: {all_researchers.count()}")
        for r in all_researchers:
            print(f"  - {r.user.get_full_name()} (ID: {r.user.user_id})")
        
        # IDs des exclus (TeamLeader et LabManager)
        team_leader_ids = set(
            TeamLeader.objects.filter(end_date__isnull=True).values_list('user_id', flat=True)
        )
        lab_manager_ids = set(
            LabManager.objects.filter(end_date__isnull=True).values_list('user_id', flat=True)
        )
        
        print(f"Team Leader IDs: {team_leader_ids}")
        print(f"Lab Manager IDs: {lab_manager_ids}")
        
        # Construire la liste des team leaders disponibles
        available_team_leaders = []
        for researcher in all_researchers:
            user = researcher.user
            user_id = user.user_id
            
            is_team_leader = user_id in team_leader_ids
            is_lab_manager = user_id in lab_manager_ids
            is_in_team = user.teams.exists()
            
            print(f"  Checking {user.get_full_name()}: team_leader={is_team_leader}, lab_manager={is_lab_manager}, in_team={is_in_team}")
            
            # Un Team Leader doit:
            # 1. Ne pas être déjà TeamLeader
            # 2. Ne pas être LabManager
            # 3. Ne pas être déjà dans une équipe
            if not is_team_leader and not is_lab_manager and not is_in_team:
                available_team_leaders.append({
                    'id': user.user_id,
                    'userId': user.user_id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'full_name': user.get_full_name() or user.username,
                    'fullName': user.get_full_name() or user.username,
                    'h_index': researcher.h_index,
                    'research_field': researcher.research_field or 'Non spécifié',
                    'isInTeam': False,
                    'status': 'available',
                })
                print(f"  ✅ {user.get_full_name()} - Available for Team Leader")
            else:
                print(f"  ❌ Excluded: {user.get_full_name()}")
        
        print(f"Total available team leaders: {len(available_team_leaders)}")
        
        return Response(available_team_leaders)


    @action(detail=True, methods=['get'], url_path='teams')
    def institution_teams(self, request, pk=None):
        """
        GET /api/institutions/{id}/teams/
        Retourne toutes les équipes de l'institution avec leurs statistiques
        """
        from team.models import Team
        from publication.models import Publication
        from users.models import Researcher, TeamLeader
        from django.db.models import Sum
        
        institution = self.get_object()
        lab_ids = institution.laboratories.values_list('ID', flat=True)
        
        # Récupérer toutes les équipes
        teams = Team.objects.filter(laboratory__in=lab_ids)
        
        teams_data = []
        for team in teams:
            # Compter les membres
            members_count = team.members.count()
            
            # Compter les publications de l'équipe
            publications = Publication.objects.filter(
                coauthors__linked_user__teams=team,
                is_validated=True
            ).distinct()
            publications_count = publications.count()
            
            # Total des citations
            citations_count = publications.aggregate(total=Sum('citation_count'))['total'] or 0
            
            # H-Index moyen des membres
            h_indices = []
            for member in team.members.all():
                try:
                    researcher = Researcher.objects.get(user=member)
                    if researcher.h_index:
                        h_indices.append(researcher.h_index)
                except Researcher.DoesNotExist:
                    pass
            avg_h_index = sum(h_indices) / len(h_indices) if h_indices else 0
            
            # ✅ Récupérer le team leader correctement
            team_leader = None
            team_leader_id = None
            try:
                # Chercher le TeamLeader actif pour cette équipe
                team_leader_obj = TeamLeader.objects.filter(
                    team=team, 
                    end_date__isnull=True
                ).select_related('user').first()
                
                if team_leader_obj:
                    team_leader = team_leader_obj.user.get_full_name() or team_leader_obj.user.username
                    team_leader_id = team_leader_obj.user.user_id
                else:
                    # Vérifier aussi si le champ team_leader existe directement sur le modèle Team
                    if hasattr(team, 'team_leader') and team.team_leader:
                        team_leader = team.team_leader.get_full_name() or team.team_leader.username
                        team_leader_id = team.team_leader.user_id
            except Exception as e:
                print(f"Error getting team leader for team {team.ID}: {e}")
            
            teams_data.append({
                'id': team.ID,
                'name': team.name,
                'description': team.description,
                'laboratory': team.laboratory.name,
                'laboratory_id': team.laboratory.ID,
                'team_leader': team_leader,
                'team_leader_id': team_leader_id,
                'members_count': members_count,
                'publications': publications_count,
                'citations': citations_count,
                'avg_h_index': round(avg_h_index, 2),
            })
        
        return Response(teams_data)


    @action(detail=True, methods=['post'], url_path='create-team')
    def create_team(self, request, pk=None):
        """
        POST /api/institutions/{id}/create-team/
        Crée une nouvelle équipe dans l'institution
        Body: {
            "name": "Nom de l'équipe",
            "description": "Description",
            "laboratory_id": 1,
            "team_leader_id": 123 (optionnel),
            "member_ids": [1, 2, 3] (optionnel)
        }
        """
        from team.models import Team
        from laboratory.models import Laboratory
        from users.models import User, TeamLeader, LabManager
        from django.utils import timezone
        
        institution = self.get_object()
        
        name = request.data.get('name')
        description = request.data.get('description', '')
        laboratory_id = request.data.get('laboratory_id')
        team_leader_id = request.data.get('team_leader_id')
        member_ids = request.data.get('member_ids', [])
        
        if not name:
            return Response({'error': 'Team name is required'}, status=400)
        
        if not laboratory_id:
            return Response({'error': 'Laboratory is required'}, status=400)
        
        try:
            laboratory = Laboratory.objects.get(ID=laboratory_id, institution=institution)
        except Laboratory.DoesNotExist:
            return Response({'error': 'Laboratory not found'}, status=404)
        
        # Vérifier si une équipe avec ce nom existe déjà dans le laboratoire
        if Team.objects.filter(name=name, laboratory=laboratory).exists():
            return Response({'error': 'A team with this name already exists in this laboratory'}, status=400)
        
        # Créer l'équipe
        team = Team.objects.create(
            name=name,
            description=description,
            laboratory=laboratory
        )
        
        # Assigner le team leader si spécifié
        team_leader_assigned = None
        if team_leader_id:
            try:
                user = User.objects.get(user_id=team_leader_id)
                # Vérifier que l'utilisateur n'est pas déjà TeamLeader ou LabManager
                if not TeamLeader.objects.filter(user=user).exists() and not LabManager.objects.filter(user=user).exists():
                    TeamLeader.objects.create(
                        user=user,
                        team=team,
                        start_date=timezone.now().date()
                    )
                    team_leader_assigned = user.get_full_name() or user.username
                    team.team_leader = user
                    team.save()
            except User.DoesNotExist:
                pass
        
        # Ajouter les membres
        members_added = []
        for member_id in member_ids:
            try:
                user = User.objects.get(user_id=member_id)
                # Vérifier que l'utilisateur n'est pas déjà dans une autre équipe
                if not user.teams.exists():
                    team.members.add(user)
                    members_added.append(user.get_full_name() or user.username)
            except User.DoesNotExist:
                pass
        
        return Response({
            'success': True,
            'message': f'Team "{name}" created successfully',
            'team': {
                'id': team.ID,
                'name': team.name,
                'description': team.description,
                'laboratory': laboratory.name,
                'laboratory_id': laboratory.ID,
                'team_leader': team_leader_assigned,
                'members_count': len(members_added),
                'members': members_added,
            }
        }, status=201)


    @action(detail=True, methods=['put'], url_path='update-team/(?P<team_id>[^/.]+)')
    def update_team(self, request, pk=None, team_id=None):
        """
        PUT /api/institutions/{id}/update-team/{team_id}/
        Met à jour une équipe - Un seul leader par équipe
        """
        from team.models import Team
        from users.models import User, TeamLeader
        from django.utils import timezone
        
        institution = self.get_object()
        
        try:
            team = Team.objects.get(ID=team_id, laboratory__institution=institution)
        except Team.DoesNotExist:
            return Response({'error': 'Team not found'}, status=404)
        
        name = request.data.get('name')
        description = request.data.get('description')
        team_leader_id = request.data.get('team_leader_id')
        member_ids = request.data.get('member_ids', [])
        
        if name:
            team.name = name
        if description is not None:
            team.description = description
        team.save()
        
        # ✅ GESTION CORRECTE DU TEAM LEADER
        # Un seul leader par équipe
        if team_leader_id is not None:
            if team_leader_id == '' or team_leader_id is None:
                # Supprimer le team leader de cette équipe
                TeamLeader.objects.filter(team=team).delete()
                team.team_leader = None
                team.save()
            else:
                try:
                    user = User.objects.get(user_id=team_leader_id)
                    
                    # ✅ Vérifier si cet utilisateur est déjà leader d'UNE AUTRE équipe
                    existing_leader = TeamLeader.objects.filter(user=user).exclude(team=team).first()
                    
                    if existing_leader:
                        return Response({
                            'error': f'❌ {user.get_full_name()} is already the team leader of "{existing_leader.team.name}". Please remove them from that team first.'
                        }, status=400)
                    
                    # ✅ Supprimer l'ancien leader de CETTE équipe (s'il existe)
                    TeamLeader.objects.filter(team=team).delete()
                    
                    # ✅ Créer le nouveau leader
                    TeamLeader.objects.create(
                        user=user,
                        team=team,
                        start_date=timezone.now().date()
                    )
                    
                    team.team_leader = user
                    team.save()
                    
                except User.DoesNotExist:
                    return Response({'error': 'User not found'}, status=404)
        
        # Gérer les membres
        if member_ids:
            team.members.clear()
            for member_id in member_ids:
                try:
                    user = User.objects.get(user_id=member_id)
                    # ✅ Ne pas ajouter le leader comme membre (il est déjà leader)
                    if team_leader_id and member_id == team_leader_id:
                        continue
                    team.members.add(user)
                except User.DoesNotExist:
                    pass
        
        return Response({
            'success': True,
            'message': f'Team "{team.name}" updated successfully',
            'team': {
                'id': team.ID,
                'name': team.name,
                'description': team.description,
                'team_leader': team.team_leader.get_full_name() if team.team_leader else None,
                'team_leader_id': team.team_leader.user_id if team.team_leader else None,
                'members_count': team.members.count(),
            }
        })


    @action(detail=True, methods=['delete'], url_path='delete-team/(?P<team_id>[^/.]+)')
    def delete_team(self, request, pk=None, team_id=None):
        """
        DELETE /api/institutions/{id}/delete-team/{team_id}/
        Supprime une équipe
        """
        from team.models import Team
        
        institution = self.get_object()
        
        try:
            team = Team.objects.get(ID=team_id, laboratory__institution=institution)
            team_name = team.name
            team.delete()
            
            return Response({
                'success': True,
                'message': f'Team "{team_name}" deleted successfully'
            })
        except Team.DoesNotExist:
            return Response({'error': 'Team not found'}, status=404)
    @action(detail=True, methods=['get'], url_path='address')
    def get_institution_address(self, request, pk=None):
        """
        GET /api/institutions/{id}/address/
        Retourne l'adresse complète de l'institution (Ville, Wilaya, Pays)
        """
        institution = self.get_object()
        
        address_parts = []
        
        if institution.ville:
            address_parts.append(institution.ville.name)
            
            if institution.ville.wilaya:
                address_parts.append(institution.ville.wilaya.name)
                
                if institution.ville.wilaya.country:
                    address_parts.append(institution.ville.wilaya.country.name)
        
        full_address = ', '.join(address_parts) if address_parts else 'No address information'
        
        return Response({
            'full_address': full_address,
            'city': institution.ville.name if institution.ville else None,
            'wilaya': institution.ville.wilaya.name if institution.ville and institution.ville.wilaya else None,
            'country': institution.ville.wilaya.country.name if institution.ville and institution.ville.wilaya and institution.ville.wilaya.country else None,
        })