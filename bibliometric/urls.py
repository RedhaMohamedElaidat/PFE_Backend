# bibliometric/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.bibliometrix_dashboard, name='dashboard'),
    path('summary/', views.bibliometrix_summary, name='summary'),
    path('top-authors/', views.bibliometrix_top_authors, name='top-authors'),
    path('thematic-clusters/', views.bibliometrix_thematic_clusters, name='thematic-clusters'),
    path('collaboration-network/', views.bibliometrix_collaboration_network, name='collaboration-network'),
    path('all-analyses/', views.bibliometrix_all_analyses, name='all-analyses'),
    path('ranking/', views.researcher_ranking, name='ranking'),
    path('researcher/<int:researcher_id>/', views.researcher_bibliometric, name='researcher-by-id'),
    path('researcher/name/<str:name>/', views.researcher_bibliometric_by_name, name='researcher-by-name'),
    path('researcher/<int:researcher_id>/refresh/', views.refresh_researcher_cache, name='refresh-cache'),
]