# citation/views.py
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend # type: ignore
from citation.models import Citation, DataSource
from citation.serializers import CitationSerializer, CitationCreateSerializer


class CitationViewSet(viewsets.ModelViewSet):
    queryset = Citation.objects.select_related(
        'citing_publication', 'cited_publication'
    )
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ['source', 'citation_date']
    ordering_fields    = ['citation_date']
    ordering           = ['-citation_date']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return CitationCreateSerializer
        return CitationSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    # ── Actions spécifiques ───────────────────────────────────────────────

    @action(detail=False, methods=['get'])
    def by_publication(self, request):
        """
        GET /api/citations/by_publication/?id=X
        Retourne toutes les citations reçues par une publication.
        """
        pub_id = request.query_params.get('id')
        if not pub_id:
            return Response(
                {'error': 'Paramètre id requis.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        qs = Citation.objects.filter(
            cited_publication_id=pub_id
        ).select_related('citing_publication')
        return Response(CitationSerializer(qs, many=True).data)

    @action(detail=False, methods=['get'])
    def co_citations(self, request):
        """
        GET /api/citations/co_citations/?id=X
        Trouve les publications souvent citées ensemble avec la publication X.
        Utilisé pour construire le graphe de co-citations.
        """
        from django.db.models import Count
        pub_id = request.query_params.get('id')
        if not pub_id:
            return Response(
                {'error': 'Paramètre id requis.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Publications qui citent aussi les mêmes sources que pub_id
        co_cited = (
            Citation.objects
            .filter(
                citing_publication__citations_made__cited_publication_id=pub_id
            )
            .exclude(cited_publication_id=pub_id)
            .values(
                'cited_publication_id',
                'cited_publication__title'
            )
            .annotate(co_citation_count=Count('id'))
            .order_by('-co_citation_count')[:20]
        )
        return Response(list(co_cited))

    @action(detail=False, methods=['get'])
    def sources_stats(self, request):
        """
        GET /api/citations/sources_stats/
        Nombre de citations par source (OpenAlex, Scopus...).
        """
        from django.db.models import Count
        stats = (
            Citation.objects
            .values('source')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        return Response(list(stats))