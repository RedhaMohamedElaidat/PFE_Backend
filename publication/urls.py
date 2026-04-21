# laboratory/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from publication.views import PublicationViewSet

router = DefaultRouter()
router.register(r'publications', PublicationViewSet, basename='publication')

urlpatterns = [path('', include(router.urls))]


