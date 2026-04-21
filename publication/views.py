# publication/viewsets.py - VERSION CORRIGÉE

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q

from publication.models import Publication
from publication.serializers import (
    PublicationSerializer,
    PublicationCreateSerializer,
    PublicationListSerializer,
)

class PublicationViewSet(viewsets.ModelViewSet):

    queryset = (
        Publication.objects
        .select_related('journal', 'institution')
        .prefetch_related('keywords', 'coauthors__linked_user')
    )

    permission_classes = [AllowAny]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['type', 'publication_year', 'is_validated', 'institution', 'journal']
    search_fields = ['title', 'abstract', 'doi', 'keywords__label']
    ordering_fields = ['publication_year', 'citation_count', 'altmetric_score']
    ordering = ['-publication_year']

    def get_serializer_class(self):
        if self.action == 'list':
            return PublicationListSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return PublicationCreateSerializer
        return PublicationSerializer

    def get_permissions(self):
        if self.action in ['destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def validate(self, request, pk=None):
        pub = self.get_object()
        pub.validate()
        return Response({'detail': f'Publication "{pub.title[:50]}" validée.'})

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def reject(self, request, pk=None):
        pub = self.get_object()
        pub.is_validated = False
        pub.save(update_fields=['is_validated'])
        return Response({'detail': f'Publication "{pub.title[:50]}" rejetée.'})

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        pub = self.get_object()
        return Response({
            'citation_count': pub.get_citation_count(),
            'impact_factor': pub.get_impact_factor(),
            'altmetric_score': pub.get_altmetric_score(),
        })

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def refresh_citations(self, request, pk=None):
        pub = self.get_object()
        pub.refresh_citation_count()
        return Response({'citation_count': pub.citation_count})

    @action(detail=False, methods=['get'])
    def pending(self, request):
        qs = self.get_queryset().filter(is_validated=False)
        return Response(PublicationListSerializer(qs, many=True).data)

    @action(detail=False, methods=['get'])
    def top_cited(self, request):
        n = int(request.query_params.get('n', 10))
        year = request.query_params.get('year')

        qs = self.get_queryset().filter(is_validated=True).order_by('-citation_count')

        if year:
            qs = qs.filter(publication_year=year)

        return Response(PublicationListSerializer(qs[:n], many=True).data)

    @action(detail=True, methods=['get'])
    def coauthors(self, request, pk=None):
        from coAuthor.models import CoAuthor
        from coAuthor.serializers import CoAuthorSerializer

        pub = self.get_object()
        coauthors = CoAuthor.objects.filter(
            publication=pub
        ).select_related('linked_user')
        return Response(CoAuthorSerializer(coauthors, many=True).data)

    @action(detail=True, methods=['get'])
    def citations(self, request, pk=None):
        from citation.models import Citation
        from citation.serializers import CitationSerializer

        pub = self.get_object()
        received = Citation.objects.filter(
            cited_publication=pub
        ).select_related('citing_publication')
        return Response(CitationSerializer(received, many=True).data)

    @action(detail=False, methods=['get'], url_path='my-publications')
    def my_publications(self, request):
        """
        GET /api/publications/my-publications/
        """
        from users.models import Researcher
        from coAuthor.models import CoAuthor

        user = request.user

        try:
            researcher = Researcher.objects.get(user=user)
        except Researcher.DoesNotExist:
            return Response(
                {"detail": "Aucun profil chercheur associé à cet utilisateur."},
                status=status.HTTP_404_NOT_FOUND
            )

        publication_ids = CoAuthor.objects.filter(
            Q(linked_user=user) |
            Q(author_orcid=researcher.orcid)
        ).values_list('publication_id', flat=True).distinct()

        publications = self.get_queryset().filter(
            id__in=publication_ids
        )

        print(f"\n📊 DEBUG MY PUBLICATIONS")
        print(f"User: {user}")
        print(f"ORCID: {researcher.orcid}")
        print(f"Publications trouvées: {publications.count()}\n")

        serializer = self.get_serializer(publications, many=True)
        return Response(serializer.data)

    # ========== MÉTHODE CORRIGÉE - UNE SEULE VERSION ==========
    
    @action(detail=False, methods=['get'], url_path='by-researcher')
    def publications_by_researcher(self, request):
        """
        GET /api/publications/by-researcher/?user_id=123
        """
        from users.models import User, Researcher
        from coAuthor.models import CoAuthor
        
        user_id = request.query_params.get('user_id')
        
        if not user_id:
            return Response(
                {"detail": "Veuillez fournir user_id."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Note: Utilisez 'id' ou 'user_id' selon votre modèle User
            user = User.objects.get(user_id=user_id)
        except User.DoesNotExist:
            return Response(
                {"detail": f"Utilisateur avec l'ID {user_id} non trouvé."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Récupérer l'ORCID du chercheur
        orcid = None
        try:
            researcher = Researcher.objects.get(user=user)
            orcid = researcher.orcid
        except Researcher.DoesNotExist:
            pass
        
        # Récupérer les IDs des publications
        publication_ids = CoAuthor.objects.filter(
            Q(linked_user=user) |
            (Q(author_orcid=orcid) if orcid else Q())
        ).values_list('publication_id', flat=True).distinct()
        
        # Récupérer les publications
        publications = self.get_queryset().filter(
            id__in=publication_ids,
            is_validated=True
        ).order_by('-publication_year')
        
        print(f"\n📊 PUBLICATIONS FOR RESEARCHER {user_id}")
        print(f"User: {user.username} ({user.get_full_name()})")
        print(f"ORCID: {orcid}")
        print(f"Publications trouvées: {publications.count()}\n")
        
        serializer = self.get_serializer(publications, many=True)
        return Response({
            'user_id': user_id,
            'username': user.username,
            'full_name': user.get_full_name(),
            'publications': serializer.data,
            'total': publications.count()
        })

    def get_queryset(self):
        return self.queryset