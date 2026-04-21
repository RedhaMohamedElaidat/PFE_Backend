# coAuthor/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from coAuthor.views import CoAuthorViewSet

router = DefaultRouter()
router.register(r'coauthors', CoAuthorViewSet, basename='coauthor')

urlpatterns = [path('', include(router.urls))]