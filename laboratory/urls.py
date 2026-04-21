# laboratory/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from laboratory.views import LaboratoryViewSet

router = DefaultRouter()
router.register(r'laboratories', LaboratoryViewSet, basename='laboratory')

urlpatterns = [path('', include(router.urls))]