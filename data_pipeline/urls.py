# data_pipeline/urls.py
from django.urls import path
from data_pipeline.views import (
    VerifyOrcidView,
    SaveOrcidAndSyncView,
    SyncPublicationsView,
)

urlpatterns = [
    path('verify-orcid/', VerifyOrcidView.as_view(),       name='verify-orcid'),
    path('save-orcid/',   SaveOrcidAndSyncView.as_view(),  name='save-orcid'),
    path('sync/',         SyncPublicationsView.as_view(),  name='sync-publications'),
]