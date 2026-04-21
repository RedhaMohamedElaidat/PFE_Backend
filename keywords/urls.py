# keywords/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from keywords.views import KeywordViewSet

router = DefaultRouter()
router.register(r'keywords', KeywordViewSet, basename='keyword')

urlpatterns = [path('', include(router.urls))]