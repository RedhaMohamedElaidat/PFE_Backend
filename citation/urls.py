# citation/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from citation.views import CitationViewSet

router = DefaultRouter()
router.register(r'citations', CitationViewSet, basename='citation')

urlpatterns = [path('', include(router.urls))]