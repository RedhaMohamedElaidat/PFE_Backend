# team/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from team.views import TeamViewSet

router = DefaultRouter()
# Enregistrer avec un préfixe vide car "teams" est déjà dans l'URL principale
router.register(r'', TeamViewSet, basename='team')

urlpatterns = [
    path('', include(router.urls)),
]
