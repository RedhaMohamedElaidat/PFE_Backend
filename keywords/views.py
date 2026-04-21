# keywords/views.py
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend # type: ignore
from keywords.models import Keyword
from keywords.serializers import KeywordSerializer, KeywordCreateSerializer


class KeywordViewSet(viewsets.ModelViewSet):
    queryset           = Keyword.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['label']
    ordering_fields    = ['label']
    ordering           = ['label']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return KeywordCreateSerializer
        return KeywordSerializer

    def get_permissions(self):
        # Lecture accessible à tous les authentifiés
        # Création / modification / suppression réservées aux admins
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'])
    def top(self, request):
        """
        GET /api/keywords/top/?n=20
        Retourne les keywords les plus utilisés dans les publications.
        """
        from django.db.models import Count
        n  = int(request.query_params.get('n', 20))
        qs = (
            Keyword.objects
            .annotate(pub_count=Count('publications'))
            .filter(pub_count__gt=0)
            .order_by('-pub_count')[:n]
        )
        data = [
            {'ID': kw.ID, 'label': kw.label, 'pub_count': kw.pub_count}
            for kw in qs
        ]
        return Response(data)