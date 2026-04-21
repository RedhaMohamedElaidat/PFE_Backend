# journal/views.py

from rest_framework import viewsets, filters

from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser

from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend   # type: ignore

from journal.models import Journal
from journal.serializers import JournalSerializer, JournalCreateSerializer

class JournalViewSet(viewsets.ModelViewSet):
    queryset           = Journal.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['name', 'issn']
    ordering_fields    = ['name', 'impact_factor']
    ordering           = ['-impact_factor']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return JournalCreateSerializer
        return JournalSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'])
    def top_impact(self, request):
        """GET /api/journals/top_impact/?n=10"""
        n  = int(request.query_params.get('n', 10))
        qs = Journal.objects.filter(
            impact_factor__isnull=False
        ).order_by('-impact_factor')[:n]
        return Response(JournalSerializer(qs, many=True).data)