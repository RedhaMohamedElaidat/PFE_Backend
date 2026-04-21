# team/views.py - Version corrigée avec distinction internal/external

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Avg, Sum, Count, Q
from team.models import Team
from team.serializers import (
    TeamSerializer, TeamDetailSerializer,
    TeamCreateSerializer, TeamMemberSerializer
)


class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.select_related('laboratory').prefetch_related('members')
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['laboratory']
    search_fields = ['name', 'description']
    ordering_fields = ['name']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return TeamDetailSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return TeamCreateSerializer
        return TeamSerializer

    def get_permissions(self):
        
        return [IsAuthenticated()]

    # ── Membres ───────────────────────────────────────────────────────────

    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        """GET /api/teams/{id}/members/"""
        team = self.get_object()
        return Response(TeamMemberSerializer(team.members.all(), many=True).data)
    @action(detail=False, methods=['get'], url_path='members')
    def all_team_members(self, request):
        """
        GET /api/teams/members/
        Retourne tous les membres de toutes les équipes (pour l'institution director)
        """
        from users.models import User
        
        # Récupérer tous les utilisateurs qui sont membres d'au moins une équipe
        team_members = User.objects.filter(teams__isnull=False).distinct()
        
        # Sérialiser les données
        members_data = []
        for member in team_members:
            members_data.append({
                'user_id': member.user_id,
                'username': member.username,
                'email': member.email,
                'first_name': member.first_name,
                'last_name': member.last_name,
                'full_name': member.get_full_name() or member.username,
            })
        
        return Response(members_data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def add_member(self, request, pk=None):
        """POST /api/teams/{id}/add_member/ — body: {user_id: X}"""
        team = self.get_object()
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({'error': 'user_id requis.'}, status=status.HTTP_400_BAD_REQUEST)
        from users.models import User
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({'error': 'Utilisateur introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        team.members.add(user)
        return Response({'detail': f'{user.get_full_name()} ajouté à {team.name}.'})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def remove_member(self, request, pk=None):
        """POST /api/teams/{id}/remove_member/ — body: {user_id: X}"""
        team = self.get_object()
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({'error': 'user_id requis.'}, status=status.HTTP_400_BAD_REQUEST)
        from users.models import User
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({'error': 'Utilisateur introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        team.members.remove(user)
        return Response({'detail': f'{user.get_full_name()} retiré de {team.name}.'})

    # ── Stats ─────────────────────────────────────────────────────────────

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """GET /api/teams/{id}/stats/"""
        from users.models import Researcher
        from publication.models import Publication
        from coAuthor.models import CoAuthor

        team = self.get_object()
        
        members = team.members.all()
        member_count = members.count()
        
        avg_h_index = 0
        if member_count > 0:
            member_ids = [member.user_id for member in members]
            researchers = Researcher.objects.filter(user_id__in=member_ids)
            avg_result = researchers.aggregate(avg_h=Avg('h_index'))
            avg_h_index = avg_result['avg_h'] or 0
        
        total_pubs = 0
        total_citations = 0
        
        if member_count > 0:
            publication_ids = set()
            
            for member in members:
                coauthors = CoAuthor.objects.filter(linked_user=member)
                for coauthor in coauthors:
                    if coauthor.publication and coauthor.publication.is_validated:
                        publication_ids.add(coauthor.publication.id)
            
            if publication_ids:
                publications = Publication.objects.filter(
                    id__in=publication_ids,
                    is_validated=True
                )
                total_pubs = publications.count()
                total_citations = publications.aggregate(total=Sum('citation_count'))['total'] or 0
        
        leader = team.current_leader
        leader_name = leader.get_full_name() if leader else None

        return Response({
            'team_name': team.name,
            'member_count': member_count,
            'avg_h_index': round(avg_h_index, 2),
            'total_pubs': total_pubs,
            'total_citations': total_citations,
            'leader': leader_name,
        })
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def set_leader(self, request, pk=None):
        """POST /api/teams/{id}/set_leader/ — body: {user_id: X}"""
        team = self.get_object()
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({'error': 'user_id requis.'}, status=status.HTTP_400_BAD_REQUEST)
        
        from users.models import User, TeamLeader
        from django.utils import timezone
        
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({'error': 'Utilisateur introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        
        # Terminer l'ancien leader si existe
        TeamLeader.objects.filter(team=team, end_date__isnull=True).update(end_date=timezone.now().date())
        
        # Créer le nouveau leader
        TeamLeader.objects.create(user=user, team=team, start_date=timezone.now().date())
        
        return Response({'detail': f'{user.get_full_name()} est maintenant leader de {team.name}.'})

    # ── COLLABORATIONS ─────────────────────────────────────────────────────

    @action(detail=True, methods=['get'], url_path='collaborations')
    def collaborations(self, request, pk=None):
        """
        GET /api/teams/{id}/collaborations/
        
        Retourne les collaborations de l'équipe:
        - Internal: AUTRES membres de l'équipe (exclut le membre lui-même)
        - External: coauthors qui ne sont PAS membres de l'équipe
        """
        from coAuthor.models import CoAuthor
        from publication.models import Publication
        
        team = self.get_object()
        members = team.members.all()
        
        if not members.exists():
            return Response({
                'team_id': team.ID,
                'team_name': team.name,
                'total_collaborators': 0,
                'internal_collabs': 0,
                'external_collabs': 0,
                'countries': 0,
                'internal_collaborators': [],
                'external_collaborators': [],
                'top_collaborators': [],
                'geographic_distribution': [],
                'timeline': [],
            })
        
        member_ids = set(m.user_id for m in members)
        member_names = {}
        for m in members:
            full_name = m.get_full_name().strip()
            if full_name:
                member_names[full_name.lower()] = m.user_id
        
        print(f"🔵 Team: {team.name}")
        print(f"👥 Members: {list(member_ids)}")
        
        # ÉTAPE 1: Récupérer les coauthors liés aux membres
        team_coauthors = CoAuthor.objects.filter(
            linked_user_id__in=member_ids
        ).select_related('publication', 'linked_user')
        
        print(f"📊 CoAuthors of team members: {team_coauthors.count()}")
        
        # ÉTAPE 2: Récupérer les IDs des publications
        team_publication_ids = set()
        member_publication_map = {}  # publication_id -> list of member_ids
        
        for ca in team_coauthors:
            if ca.publication:
                pub_id = ca.publication.id
                team_publication_ids.add(pub_id)
                
                if pub_id not in member_publication_map:
                    member_publication_map[pub_id] = set()
                if ca.linked_user_id:
                    member_publication_map[pub_id].add(ca.linked_user_id)
        
        print(f"📚 Publications with team members: {len(team_publication_ids)}")
        
        # ÉTAPE 3: Récupérer TOUS les coauthors sur ces publications
        all_publication_coauthors = CoAuthor.objects.filter(
            publication_id__in=team_publication_ids
        ).select_related('publication', 'linked_user')
        
        print(f"🤝 Total collaborators: {all_publication_coauthors.count()}")
        
        # ÉTAPE 4: Analyser les collaborations
        collaborators_dict = {}
        internal_collabs = []
        external_collabs = []
        geographic_distribution = {}
        timeline_data = {}
        
        for ca in all_publication_coauthors:
            if not ca.publication:
                continue
            
            pub_id = ca.publication.id
            current_coauthor_user_id = ca.linked_user_id
            
            # ─────────────────────────────────────────────────────────────
            # DÉTERMINER SI INTERNE OU EXTERNE
            # ─────────────────────────────────────────────────────────────
            
            is_internal = False
            
            if current_coauthor_user_id and current_coauthor_user_id in member_ids:
                # Ce coauthor est un membre de l'équipe
                # Vérifier s'il y a AU MOINS UN AUTRE membre sur cette publication
                members_on_this_pub = member_publication_map.get(pub_id, set())
                
                # Si plus d'1 membre sur cette publication, c'est une collaboration interne
                # Sinon, c'est le membre seul (on ne le compte PAS comme collaborateur)
                if len(members_on_this_pub) > 1:
                    is_internal = True
                else:
                    # Le membre est seul sur cette publication, on l'ignore
                    continue
            else:
                # Pas un membre de l'équipe -> externe
                is_internal = False
            
            # ─────────────────────────────────────────────────────────────
            # CLÉ UNIQUE POUR LE COLLABORATEUR
            # ─────────────────────────────────────────────────────────────
            
            if ca.author_orcid:
                collaborator_key = ca.author_orcid
            elif current_coauthor_user_id:
                collaborator_key = f"user-{current_coauthor_user_id}"
            else:
                collaborator_key = f"coauthor-{ca.ID}"
            
            # ─────────────────────────────────────────────────────────────
            # CRÉER/METTRE À JOUR LE COLLABORATEUR
            # ─────────────────────────────────────────────────────────────
            
            if collaborator_key not in collaborators_dict:
                # Déterminer le nom
                if ca.linked_user:
                    name = ca.linked_user.get_full_name() or ca.author_name or 'Unknown'
                else:
                    name = ca.author_name or 'Unknown'
                
                collaborators_dict[collaborator_key] = {
                    'id': ca.ID,
                    'name': name,
                    'orcid': ca.author_orcid,
                    'institution': self._extract_institution(ca.affiliation_at_time),
                    'affiliation': ca.affiliation_at_time,
                    'type': 'internal' if is_internal else 'external',
                    'publication_count': 0,
                    'publications': []
                }
            
            collab = collaborators_dict[collaborator_key]
            collab['publication_count'] += 1
            
            pub_entry = {
                'id': ca.publication.id,
                'title': ca.publication.title,
                'year': ca.publication.publication_year,
                'citations': ca.publication.citation_count,
            }
            
            if pub_entry not in collab['publications']:
                collab['publications'].append(pub_entry)
            
            # ─────────────────────────────────────────────────────────────
            # DISTRIBUTION GÉOGRAPHIQUE (externes seulement)
            # ─────────────────────────────────────────────────────────────
            
            if not is_internal and ca.affiliation_at_time:
                country = self._extract_country(ca.affiliation_at_time)
                geographic_distribution[country] = geographic_distribution.get(country, 0) + 1
            
            # ─────────────────────────────────────────────────────────────
            # TIMELINE
            # ─────────────────────────────────────────────────────────────
            
            year = ca.publication.publication_year
            if year:
                year_str = str(year)
                if year_str not in timeline_data:
                    timeline_data[year_str] = {'year': year, 'internal': 0, 'external': 0}
                
                if is_internal:
                    timeline_data[year_str]['internal'] += 1
                else:
                    timeline_data[year_str]['external'] += 1
        
        # ÉTAPE 5: Séparer et trier
        for collab in collaborators_dict.values():
            if collab['type'] == 'internal':
                internal_collabs.append(collab)
            else:
                external_collabs.append(collab)
        
        internal_collabs.sort(key=lambda x: x['publication_count'], reverse=True)
        external_collabs.sort(key=lambda x: x['publication_count'], reverse=True)
        all_collabs = internal_collabs + external_collabs
        all_collabs.sort(key=lambda x: x['publication_count'], reverse=True)
        
        # ÉTAPE 6: Formater
        timeline = sorted(timeline_data.values(), key=lambda x: x['year'])
        
        geo_distribution = [
            {'name': country, 'value': count}
            for country, count in geographic_distribution.items()
        ]
        geo_distribution.sort(key=lambda x: x['value'], reverse=True)
        
        print(f"\n✅ Internal (other team members): {len(internal_collabs)}")
        print(f"✅ External (non-members): {len(external_collabs)}")
        print(f"✅ Countries: {len(geographic_distribution)}")
        
        return Response({
            'team_id': team.ID,
            'team_name': team.name,
            'total_collaborators': len(collaborators_dict),
            'internal_collabs': len(internal_collabs),
            'external_collabs': len(external_collabs),
            'countries': len(geographic_distribution),
            'internal_collaborators': internal_collabs[:10],
            'external_collaborators': external_collabs[:10],
            'top_collaborators': all_collabs[:20],
            'geographic_distribution': geo_distribution[:10],
            'timeline': timeline,
        })

    def _extract_institution(self, affiliation: str) -> str:
        """Extrait l'institution d'une affiliation"""
        if not affiliation:
            return 'Unknown'
        institution = affiliation.split(',')[0].strip()
        return institution if institution else 'Unknown'

    def _extract_country(self, affiliation: str) -> str:
        """Extrait le pays d'une affiliation"""
        if not affiliation:
            return 'Other'
        
        aff_lower = affiliation.lower()
        
        country_keywords = {
            'Algeria': ['algeria', 'algérie', 'alger', 'algiers', 'oran', 'constantine', 'annaba', 'blida', 'béjaïa'],
            'France': ['france', 'paris', 'lyon', 'marseille', 'toulouse', 'cnrs', 'inria'],
            'USA': ['usa', 'united states', 'america', 'california', 'new york', 'texas'],
            'UK': ['uk', 'united kingdom', 'england', 'london', 'cambridge', 'oxford'],
            'Canada': ['canada', 'quebec', 'toronto', 'montreal', 'vancouver'],
            'Germany': ['germany', 'deutschland', 'berlin', 'munich', 'hamburg'],
            'Italy': ['italy', 'italia', 'rome', 'milan', 'bologna'],
            'Spain': ['spain', 'españa', 'madrid', 'barcelona', 'valencia'],
            'Tunisia': ['tunisia', 'tunisie', 'tunis', 'sousse', 'sfax'],
            'Morocco': ['morocco', 'maroc', 'rabat', 'casablanca', 'fès'],
            'Egypt': ['egypt', 'égypte', 'cairo', 'alexandria'],
            'Saudi Arabia': ['saudi', 'saoudite', 'riyadh', 'jeddah'],
            'China': ['china', 'beijing', 'shanghai', 'tsinghua', 'peking'],
            'Japan': ['japan', 'tokyo', 'osaka', 'kyoto'],
            'India': ['india', 'delhi', 'mumbai', 'bangalore', 'iit'],
            'Australia': ['australia', 'sydney', 'melbourne', 'brisbane'],
            'Brazil': ['brazil', 'brasil', 'são paulo', 'rio'],
        }
        
        for country, keywords in country_keywords.items():
            if any(kw in aff_lower for kw in keywords):
                return country
        
        return 'Other'

    @action(detail=True, methods=['get'], url_path='leader')
    def get_leader(self, request, pk=None):
        """GET /api/teams/{id}/leader/"""
        team = self.get_object()
        leader = team.current_leader
        
        if not leader:
            return Response(
                {'error': 'Aucun leader assigné à cette équipe'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response({
            'id': leader.user_id,
            'username': leader.username,
            'email': leader.email,
            'first_name': leader.first_name,
            'last_name': leader.last_name,
            'full_name': leader.get_full_name(),
        })
    
    @action(detail=False, methods=['get'], url_path='my-team')
    def my_team(self, request):
        """GET /api/teams/my-team/"""
        user = request.user
        
        try:
            if hasattr(user, 'team_leader_profile') and user.team_leader_profile:
                team = user.team_leader_profile.team
                serializer = TeamDetailSerializer(team)
                return Response(serializer.data)
            else:
                return Response(
                    {'error': 'Vous n\'êtes pas leader d\'une équipe'},
                    status=status.HTTP_403_FORBIDDEN
                )
        except Exception as e:
            return Response(
                {'error': f'Erreur: {str(e)}'},
                status=status.HTTP_403_FORBIDDEN
            )