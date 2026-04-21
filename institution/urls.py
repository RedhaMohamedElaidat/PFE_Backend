# institution/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from institution.views import (
    CountryViewSet, WilayaViewSet
    , VilleViewSet, InstitutionViewSet
)

router = DefaultRouter()
router.register(r'countries',    CountryViewSet,     basename='country')
router.register(r'wilayas',      WilayaViewSet,      basename='wilaya')
router.register(r'villes',       VilleViewSet,       basename='ville')
router.register(r'institutions', InstitutionViewSet, basename='institution')


urlpatterns = [path('', include(router.urls))]