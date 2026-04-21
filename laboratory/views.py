# laboratory/views.py - VERSION COMPLÈTE CORRIGÉE

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from laboratory.models import Laboratory
from laboratory.serializers import (
    LaboratorySerializer, LaboratoryDetailSerializer, LaboratoryCreateSerializer
)


class LaboratoryViewSet(viewsets.ModelViewSet):
    queryset = Laboratory.objects.select_related('institution').prefetch_related('teams')
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['institution']
    search_fields = ['name', 'description']
    ordering_fields = ['name']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return LaboratoryDetailSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return LaboratoryCreateSerializer
        return LaboratorySerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """GET /api/laboratories/{id}/stats/"""
        from django.db.models import Avg, Sum, Max, Count
        from users.models import Researcher
        from publication.models import Publication
        from coAuthor.models import CoAuthor

        lab = self.get_object()
        
        # Récupérer tous les chercheurs du laboratoire
        researchers = Researcher.objects.filter(user__teams__laboratory=lab).distinct()
        researcher_count = researchers.count()
        
        # Calculer le H-Index max et moyen
        h_indices = list(researchers.exclude(h_index__isnull=True).values_list('h_index', flat=True))
        max_h_index = max(h_indices) if h_indices else 0
        avg_h_index = sum(h_indices) / len(h_indices) if h_indices else 0
        
        # ✅ CORRECTION: Compter les publications correctement
        publications = Publication.objects.filter(
            coauthors__linked_user__teams__laboratory=lab,
            is_validated=True
        ).distinct()
        
        total_publications = publications.count()
        total_citations = publications.aggregate(total=Sum('citation_count'))['total'] or 0
        
        # ✅ Calculer le productivity score correctement
        from django.utils import timezone
        current_year = timezone.now().year
        productivity_score = 0
        
        for year in range(current_year - 4, current_year + 1):
            year_pubs = publications.filter(publication_year=year).count()
            weight = year - (current_year - 4) + 1
            productivity_score += year_pubs * weight
        
        # ✅ Compter les équipes
        team_count = lab.teams.count()
        
        return Response({
            'name': lab.name,
            'team_count': team_count,
            'researcher_count': researcher_count,
            'avg_h_index': round(avg_h_index, 2),
            'max_h_index': max_h_index,
            'total_publications': total_publications,
            'total_citations': total_citations,
            'productivity_score': productivity_score,
        })

    @action(detail=True, methods=['get'])
    def teams(self, request, pk=None):
        """GET /api/laboratories/{id}/teams/"""
        from team.serializers import TeamSerializer
        lab = self.get_object()
        return Response(TeamSerializer(lab.teams.all(), many=True).data)

    @action(detail=True, methods=['get'])
    def top_researchers(self, request, pk=None):
        """GET /api/laboratories/{id}/top_researchers/?n=10"""
        from users.models import Researcher
        from users.serializers import ResearcherSerializer
        n = int(request.query_params.get('n', 10))
        lab = self.get_object()
        researchers = (
            Researcher.objects
            .filter(user__teams__laboratory=lab)
            .order_by('-h_index')
            .select_related('user')[:n]
        )
        return Response(ResearcherSerializer(researchers, many=True).data)

    @action(detail=True, methods=['get'])
    def publications(self, request, pk=None):
        """GET /api/laboratories/{id}/publications/"""
        from publication.models import Publication
        from publication.serializers import PublicationSerializer
        lab = self.get_object()
        pubs = Publication.objects.filter(
            coauthors__linked_user__teams__laboratory=lab,
            is_validated=True
        ).distinct().order_by('-publication_year')
        return Response(PublicationSerializer(pubs, many=True).data)

    @action(detail=True, methods=['get'], url_path='collaborations')
    def collaborations(self, request, pk=None):
        """
        GET /api/laboratories/{id}/collaborations/
        Retourne les collaborations uniques du laboratoire (sans doublons)
        """
        from coAuthor.models import CoAuthor
        from team.models import Team
        from users.models import User
        
        lab = self.get_object()
        lab_id = lab.ID
        
        # Récupérer toutes les équipes du laboratoire
        lab_teams = Team.objects.filter(laboratory=lab)
        
        if not lab_teams.exists():
            return Response({
                'lab_id': lab_id,
                'lab_name': lab.name,
                'total_collaborators': 0,
                'internal_collabs': 0,
                'external_collabs': 0,
                'total_publications': 0,
                'countries': 0,
                'internal_collaborators': [],
                'external_collaborators': [],
                'top_collaborators': [],
                'geographic_distribution': [],
                'timeline': [],
            })
        
        # Récupérer TOUS les membres de TOUTES les équipes du laboratoire
        lab_member_ids = set()
        lab_member_details = {}
        
        for team in lab_teams:
            for member in team.members.all():
                uid = member.user_id
                lab_member_ids.add(uid)
                if uid not in lab_member_details:
                    try:
                        researcher = member.researcher_profile
                        h_index = researcher.h_index or 0
                    except:
                        h_index = 0
                    
                    lab_member_details[uid] = {
                        'id': uid,
                        'name': member.get_full_name() or member.username,
                        'email': member.email,
                        'h_index': h_index,
                    }
        
        print(f"🔵 Laboratory: {lab.name}")
        print(f"👥 Total members in lab: {len(lab_member_ids)}")
        
        if not lab_member_ids:
            return Response({
                'lab_id': lab_id,
                'lab_name': lab.name,
                'total_collaborators': 0,
                'internal_collabs': 0,
                'external_collabs': 0,
                'total_publications': 0,
                'countries': 0,
                'internal_collaborators': [],
                'external_collaborators': [],
                'top_collaborators': [],
                'geographic_distribution': [],
                'timeline': [],
            })
        
        # ÉTAPE 1: Récupérer toutes les publications du laboratoire
        lab_publication_ids = set(
            CoAuthor.objects.filter(
                linked_user_id__in=lab_member_ids
            ).values_list('publication_id', flat=True)
        )
        
        print(f"📚 Publications with lab members: {len(lab_publication_ids)}")
        
        # ÉTAPE 2: Récupérer TOUS les coauthors sur ces publications
        all_coauthors = CoAuthor.objects.filter(
            publication_id__in=lab_publication_ids
        ).select_related('publication', 'linked_user')
        
        print(f"🤝 Total coauthor entries: {all_coauthors.count()}")
        
        # ÉTAPE 3: Agréger par collaborateur UNIQUE
        collaborators_dict = {}
        publication_counts = {}
        country_counts = {}
        
        # Dictionnaire pour compter les publications UNIQUES par membre interne
        internal_publications_count = {uid: set() for uid in lab_member_ids}
        
        for ca in all_coauthors:
            if not ca.publication:
                continue
            
            pub_year = ca.publication.publication_year or 2024
            pub_id = ca.publication.id
            
            # Ajouter la publication au set du membre interne
            if ca.linked_user_id and ca.linked_user_id in lab_member_ids:
                internal_publications_count[ca.linked_user_id].add(pub_id)
            
            # Déterminer la clé unique du collaborateur
            if ca.linked_user_id:
                collaborator_key = f"user-{ca.linked_user_id}"
                is_internal = ca.linked_user_id in lab_member_ids
                if is_internal and ca.linked_user_id in lab_member_details:
                    name = lab_member_details[ca.linked_user_id]['name']
                else:
                    name = ca.linked_user.get_full_name() if ca.linked_user else ca.author_name or 'Unknown'
            elif ca.author_orcid:
                collaborator_key = ca.author_orcid
                is_internal = False
                name = ca.author_name or 'Unknown'
            else:
                collaborator_key = f"name-{ca.author_name}" if ca.author_name else f"coauthor-{ca.ID}"
                is_internal = False
                name = ca.author_name or 'Unknown'
            
            institution = self._extract_institution(ca.affiliation_at_time)
            
            # Initialiser ou mettre à jour le collaborateur
            if collaborator_key not in collaborators_dict:
                collaborators_dict[collaborator_key] = {
                    'id': ca.ID,
                    'key': collaborator_key,
                    'name': name,
                    'orcid': ca.author_orcid,
                    'institution': institution,
                    'affiliation': ca.affiliation_at_time,
                    'type': 'internal' if is_internal else 'external',
                    'publication_count': 0,
                    'publications': [],
                    'years_active': set(),
                    'user_id': ca.linked_user_id if is_internal else None,
                }
            
            collab = collaborators_dict[collaborator_key]
            
            # Ajouter la publication (éviter les doublons dans la liste des publications)
            pub_exists = any(p.get('id') == pub_id for p in collab['publications'])
            if not pub_exists:
                collab['publications'].append({
                    'id': pub_id,
                    'title': ca.publication.title,
                    'year': pub_year,
                    'citations': ca.publication.citation_count,
                })
            
            collab['years_active'].add(pub_year)
            
            # Comptage pour la timeline
            year_str = str(pub_year)
            if year_str not in publication_counts:
                publication_counts[year_str] = {'year': pub_year, 'internal': 0, 'external': 0}
            if is_internal:
                publication_counts[year_str]['internal'] += 1
            else:
                publication_counts[year_str]['external'] += 1
            
            # Distribution géographique
            if not is_internal and ca.affiliation_at_time:
                country = self._extract_country(ca.affiliation_at_time)
                if country not in ['Algeria', 'Algérie', 'Other']:
                    country_counts[country] = country_counts.get(country, 0) + 1
        
        # MISE À JOUR: Remplacer publication_count par le nombre de publications UNIQUES
        for collab in collaborators_dict.values():
            if collab['type'] == 'internal' and collab.get('user_id'):
                collab['publication_count'] = len(internal_publications_count.get(collab['user_id'], set()))
            else:
                collab['publication_count'] = len(collab['publications'])
            
            collab['years_active'] = sorted(list(collab['years_active']))
            collab['publications'].sort(key=lambda x: x['year'], reverse=True)
        
        # ÉTAPE 4: Séparer internes et externes
        internal_collabs = []
        external_collabs = []
        
        for collab in collaborators_dict.values():
            if collab['type'] == 'internal':
                internal_collabs.append(collab)
            else:
                external_collabs.append(collab)
        
        # Trier par nombre de publications
        internal_collabs.sort(key=lambda x: x['publication_count'], reverse=True)
        external_collabs.sort(key=lambda x: x['publication_count'], reverse=True)
        
        all_collabs = internal_collabs + external_collabs
        all_collabs.sort(key=lambda x: x['publication_count'], reverse=True)
        
        # ÉTAPE 5: Formater la timeline
        timeline = sorted(publication_counts.values(), key=lambda x: x['year'])
        
        # ÉTAPE 6: Distribution géographique
        geo_distribution = [
            {'name': country, 'value': count}
            for country, count in country_counts.items()
        ]
        geo_distribution.sort(key=lambda x: x['value'], reverse=True)
        
        total_unique_publications = len(lab_publication_ids)
        
        # ✅ Calculer la somme des publications des membres (avec chevauchements)
        sum_member_publications = sum(len(pubs) for pubs in internal_publications_count.values())
        
        print(f"\n✅ LAB COLLABORATIONS SUMMARY:")
        print(f"   Internal (lab members): {len(internal_collabs)}")
        print(f"   External (non-members): {len(external_collabs)}")
        print(f"   Total unique collaborators: {len(collaborators_dict)}")
        print(f"   Total unique publications (lab): {total_unique_publications}")
        print(f"   Sum of member publications (with overlap): {sum_member_publications}")
        print(f"   International countries: {len(country_counts)}")
        
        print(f"\n📊 PUBLICATIONS PAR MEMBRE INTERNE:")
        for uid, pubs in internal_publications_count.items():
            name = lab_member_details.get(uid, {}).get('name', f'User {uid}')
            print(f"   {name}: {len(pubs)} publications uniques")
        
        return Response({
            'lab_id': lab_id,
            'lab_name': lab.name,
            'total_collaborators': len(collaborators_dict),
            'internal_collabs': len(internal_collabs),
            'external_collabs': len(external_collabs),
            'total_publications': sum_member_publications, 
            'sum_member_publications': sum_member_publications,  # 119 - somme avec chevauchements
            'countries': len(country_counts),
            'internal_collaborators': internal_collabs,
            'external_collaborators': external_collabs,
            'top_collaborators': all_collabs,
            'geographic_distribution': geo_distribution,
            'timeline': timeline,
        })    
    def _extract_institution(self, affiliation: str) -> str:
        """Extrait l'institution d'une affiliation"""
        if not affiliation:
            return 'Unknown'
        # Prendre la première partie avant la virgule
        institution = affiliation.split(',')[0].strip()
        return institution if institution else 'Unknown'

    def _extract_country(self, affiliation: str) -> str:
        """Extrait le pays d'une affiliation"""
        if not affiliation:
            return 'Other'
        
        aff_lower = affiliation.lower()
        
        # Mapping des pays par mots-clés
        country_keywords = {
            'Algeria': ['algeria', 'algérie', 'alger', 'algiers', 'oran', 'constantine', 'annaba', 'blida', 'béjaïa', 'tlemcen', 'sétif', 'batna', 'biskra', 'tizi-ouzou', 'boumerdes', 'chlef', 'mostaganem', 'tiaret', 'mascara', 'sidi bel abbès', 'skikda', 'guelma', 'jijel', 'laghouat', 'ouargla', 'béchar', 'tamanrasset', 'el oued', 'ghardaïa'],
            'France': ['france', 'paris', 'lyon', 'marseille', 'toulouse', 'bordeaux', 'lille', 'cnrs', 'inria', 'inserm', 'sorbonne', 'strasbourg'],
            'USA': ['usa', 'united states', 'america', 'california', 'new york', 'texas', 'florida', 'pennsylvania', 'massachusetts', 'boston', 'chicago', 'stanford', 'harvard', 'mit', 'berkeley'],
            'UK': ['uk', 'united kingdom', 'england', 'britain', 'london', 'cambridge', 'oxford', 'manchester', 'edinburgh'],
            'Canada': ['canada', 'quebec', 'ontario', 'toronto', 'montreal', 'vancouver', 'ottawa', 'calgary'],
            'Germany': ['germany', 'deutschland', 'berlin', 'munich', 'hamburg', 'frankfurt', 'stuttgart', 'max planck'],
            'Italy': ['italy', 'italia', 'rome', 'milan', 'naples', 'turin', 'florence', 'bologna'],
            'Spain': ['spain', 'españa', 'madrid', 'barcelona', 'valencia', 'seville', 'bilbao'],
            'Tunisia': ['tunisia', 'tunisie', 'tunis', 'sousse', 'sfax'],
            'Morocco': ['morocco', 'maroc', 'rabat', 'casablanca', 'marrakech', 'fès'],
            'Egypt': ['egypt', 'égypte', 'cairo', 'alexandria'],
            'Saudi Arabia': ['saudi', 'saoudite', 'riyadh', 'jeddah', 'mecca'],
            'UAE': ['uae', 'emirates', 'émirats', 'dubai', 'abu dhabi'],
            'China': ['china', 'beijing', 'shanghai', 'guangzhou', 'shenzhen', 'wuhan', 'nanjing', 'tsinghua', 'peking'],
            'Japan': ['japan', 'tokyo', 'osaka', 'kyoto', 'nagoya'],
            'India': ['india', 'delhi', 'mumbai', 'bangalore', 'chennai', 'kolkata', 'iit'],
            'Australia': ['australia', 'sydney', 'melbourne', 'brisbane', 'perth'],
            'Brazil': ['brazil', 'brasil', 'são paulo', 'rio de janeiro'],
            'South Africa': ['south africa', 'cape town', 'johannesburg'],
            'Malaysia': ['malaysia', 'kuala lumpur'],
            'Indonesia': ['indonesia', 'jakarta'],
            'Pakistan': ['pakistan', 'islamabad', 'karachi', 'lahore'],
            'Iraq': ['iraq', 'baghdad', 'basrah'],
            'Qatar': ['qatar', 'doha'],
            'Kuwait': ['kuwait'],
            'Oman': ['oman', 'muscat'],
            'Jordan': ['jordan', 'amman'],
            'Lebanon': ['lebanon', 'beyrouth', 'beirut'],
            'Turkey': ['turkey', 'türkiye', 'istanbul', 'ankara'],
            'Russia': ['russia', 'moscow', 'saint petersburg'],
            'Portugal': ['portugal', 'lisbon', 'porto'],
            'Greece': ['greece', 'athens'],
            'Poland': ['poland', 'warsaw', 'krakow'],
            'Austria': ['austria', 'vienna'],
            'Ireland': ['ireland', 'dublin'],
            'Mexico': ['mexico', 'mexico city'],
            'Argentina': ['argentina', 'buenos aires'],
            'Chile': ['chile', 'santiago'],
            'Colombia': ['colombia', 'bogota'],
            'South Korea': ['south korea', 'korea', 'seoul'],
            'Singapore': ['singapore'],
            'Thailand': ['thailand', 'bangkok'],
            'Vietnam': ['vietnam', 'hanoi'],
            'Iran': ['iran', 'tehran'],
        }
        
        for country, keywords in country_keywords.items():
            if any(kw in aff_lower for kw in keywords):
                return country
        
        return 'Other'
    @action(detail=True, methods=['get'], url_path='publications/by-year')
    def publications_by_year(self, request, pk=None):
        """
        GET /api/laboratories/{id}/publications/by-year/
        Retourne les publications groupées par année
        """
        lab = self.get_object()
        pubs_by_year = lab.get_team_publications_by_year()
        
        # Compléter avec les années manquantes (2021-2025)
        current_year = 2025
        existing_years = {item['publication_year']: item['count'] for item in pubs_by_year}
        
        result = []
        for year in range(2021, current_year + 1):
            result.append({
                'year': year,
                'publications': existing_years.get(year, 0)
            })
        
        return Response(result)
    
    @action(detail=True, methods=['get'], url_path='members/detailed')
    def members_detailed(self, request, pk=None):
        """
        GET /api/laboratories/{id}/members/detailed/
        Retourne tous les membres avec leurs statistiques détaillées
        """
        from users.models import Researcher
        from team.serializers import TeamMemberSerializer
        
        lab = self.get_object()
        members = lab.get_all_team_members()
        
        # Enrichir avec les données des chercheurs
        member_data = []
        for member in members:
            try:
                researcher = Researcher.objects.get(user=member)
                member_data.append({
                    'user_id': member.user_id,
                    'username': member.username,
                    'email': member.email,
                    'first_name': member.first_name,
                    'last_name': member.last_name,
                    'full_name': member.get_full_name(),
                    'h_index': researcher.h_index or 0,
                    'research_field': researcher.research_field or 'Non spécifié',
                    'orcid': researcher.orcid,
                    'publication_count': researcher.publications.count() if hasattr(researcher, 'publications') else 0,
                })
            except Researcher.DoesNotExist:
                member_data.append({
                    'user_id': member.user_id,
                    'username': member.username,
                    'email': member.email,
                    'first_name': member.first_name,
                    'last_name': member.last_name,
                    'full_name': member.get_full_name(),
                    'h_index': 0,
                    'research_field': 'Non chercheur',
                    'orcid': None,
                    'publication_count': 0,
                })
        
        # Trier par h-index
        member_data.sort(key=lambda x: x['h_index'], reverse=True)
        
        return Response({
            'total_members': len(member_data),
            'members': member_data
        })
    
    @action(detail=True, methods=['get'], url_path='publications/recent')
    def recent_publications(self, request, pk=None):
        """
        GET /api/laboratories/{id}/publications/recent/
        Retourne les 10 dernières publications du laboratoire
        """
        from publication.models import Publication
        from publication.serializers import PublicationSerializer
        
        lab = self.get_object()
        limit = int(request.query_params.get('limit', 10))
        
        publications = Publication.objects.filter(
            coauthors__linked_user__teams__laboratory=lab,
            is_validated=True
        ).distinct().order_by('-publication_year', '-id')[:limit]
        
        return Response(PublicationSerializer(publications, many=True).data)
    
    @action(detail=True, methods=['get'], url_path='collaborations/international')
    def international_collaborations(self, request, pk=None):
        """
        GET /api/laboratories/{id}/collaborations/international/
        Retourne les collaborations internationales du laboratoire
        """
        lab = self.get_object()
        
        # Appeler l'endpoint collaborations existant
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        fake_request = factory.get(f'/api/laboratories/{lab.ID}/collaborations/')
        fake_request.query_params = request.query_params
        
        # Créer une instance de la vue et appeler la méthode
        response = self.collaborations(fake_request, pk=pk)
        
        if response.status_code == 200:
            data = response.data
            
            # Filtrer pour ne garder que les collaborations internationales
            # (celles qui ne sont pas en Algérie)
            international_collabs = []
            for collab in data.get('external_collaborators', []):
                if collab.get('institution') and collab.get('institution') != 'Unknown':
                    # Vérifier si l'institution est internationale
                    country = self._extract_country(collab.get('affiliation', ''))
                    if country not in ['Algeria', 'Other']:
                        international_collabs.append({
                            **collab,
                            'country': country
                        })
            
            return Response({
                'lab_id': lab.ID,
                'lab_name': lab.name,
                'total_international_collaborations': len(international_collabs),
                'international_collaborators': international_collabs[:20],
            })
        
        return response
    
    @action(detail=True, methods=['get'], url_path='dashboard')
    def dashboard_data(self, request, pk=None):
        """GET /api/laboratories/{id}/dashboard/"""
        from django.db.models import Avg, Sum, Count
        from users.models import Researcher
        from publication.models import Publication
        from team.serializers import TeamSerializer
        from coAuthor.models import CoAuthor
        
        lab = self.get_object()
        
        # Récupérer les données
        researchers = Researcher.objects.filter(user__teams__laboratory=lab).distinct()
        researcher_count = researchers.count()
        
        # Publications
        publications = Publication.objects.filter(
            coauthors__linked_user__teams__laboratory=lab,
            is_validated=True
        ).distinct()
        total_publications_unique = publications.count()
        total_citations = publications.aggregate(total=Sum('citation_count'))['total'] or 0
        
        # H-Index
        h_indices = list(researchers.exclude(h_index__isnull=True).values_list('h_index', flat=True))
        max_h_index = max(h_indices) if h_indices else 0
        avg_h_index = sum(h_indices) / len(h_indices) if h_indices else 0
        
        # Productivity score
        from django.utils import timezone
        current_year = timezone.now().year
        productivity_score = 0
        for year in range(current_year - 4, current_year + 1):
            year_pubs = publications.filter(publication_year=year).count()
            weight = year - (current_year - 4) + 1
            productivity_score += year_pubs * weight
        
        # Publications par année
        pubs_by_year = []
        for year in range(2021, current_year + 1):
            count = publications.filter(publication_year=year).count()
            pubs_by_year.append({'year': year, 'publications': count})
        
        # Top researchers
        top_researchers = []
        for r in researchers.order_by('-h_index')[:5]:
            top_researchers.append({
                'user_id': r.user.user_id,
                'username': r.user.username,
                'full_name': r.user.get_full_name() or r.user.username,
                'h_index': r.h_index or 0,
                'research_field': r.research_field or 'Non spécifié',
                'publication_count': r.publications.count() if hasattr(r, 'publications') else 0,
            })
        
        # Teams
        teams_data = TeamSerializer(lab.teams.all(), many=True).data
        
        # ✅ CALCUL COMPLET DES COLLABORATIONS
        lab_member_ids = set(researchers.values_list('user_id', flat=True))
        
        if lab_member_ids:
            # Récupérer toutes les publications des membres
            lab_publication_ids = set(
                CoAuthor.objects.filter(linked_user_id__in=lab_member_ids)
                .values_list('publication_id', flat=True)
            )
            
            # ✅ Compter les publications par membre (pour sum_member_publications)
            internal_publications_count = {}
            for uid in lab_member_ids:
                user_pubs = set(
                    CoAuthor.objects.filter(linked_user_id=uid)
                    .values_list('publication_id', flat=True)
                )
                internal_publications_count[uid] = len(user_pubs)
            
            # Compter les collaborations uniques
            all_coauthors = CoAuthor.objects.filter(publication_id__in=lab_publication_ids)
            
            collaborators_dict = {}
            for ca in all_coauthors:
                is_internal = ca.linked_user_id and ca.linked_user_id in lab_member_ids
                key = ca.author_orcid or f"user-{ca.linked_user_id}" or f"coauthor-{ca.ID}"
                
                if key not in collaborators_dict:
                    name = ca.linked_user.get_full_name() if ca.linked_user else ca.author_name or 'Unknown'
                    collaborators_dict[key] = {'type': 'internal' if is_internal else 'external'}
            
            internal_count = sum(1 for c in collaborators_dict.values() if c['type'] == 'internal')
            external_count = sum(1 for c in collaborators_dict.values() if c['type'] == 'external')
            
            # ✅ Calculer sum_member_publications (somme des publications individuelles)
            sum_member_publications = sum(internal_publications_count.values())
            
        else:
            internal_count = 0
            external_count = 0
            sum_member_publications = 0
            total_publications_unique = 0
        
        return Response({
            'laboratory': {
                'ID': lab.ID,
                'name': lab.name,
                'description': lab.description,
                'website': lab.website,
                'institution_name': lab.institution.name if lab.institution else None,
                'current_manager_name': lab.current_manager.get_full_name() if lab.current_manager else None,
            },
            'stats': {
                'team_count': lab.teams.count(),
                'researcher_count': researcher_count,
                'total_publications': total_publications_unique,
                'total_citations': total_citations,
                'avg_h_index': round(avg_h_index, 2),
                'max_h_index': max_h_index,
                'productivity_score': productivity_score,
            },
            'publications_by_year': pubs_by_year,
            'top_researchers': top_researchers,
            'teams': teams_data,
            'collaborations': {
                'total_collaborators': len(collaborators_dict) if lab_member_ids else 0,
                'internal_collabs': internal_count,
                'external_collabs': external_count,
                'countries': 0,
                'total_publications': total_publications_unique,  # ✅ AJOUTÉ
                'sum_member_publications': sum_member_publications,  # ✅ AJOUTÉ
            },
        })