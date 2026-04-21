#!/usr/bin/env python3
# bibliometric/models.py - VERSION CORRIGÉE

from django.db import models
from django.utils import timezone
from datetime import timedelta
from users.models import Researcher

# ============================================================================
# 1. ANALYSES BIBLIOMETRIX (Résultats R)
# ============================================================================

class BibliometrixAnalysis(models.Model):
    """
    Stocke les résultats complets des analyses Bibliometrix (sortie R)
    
    Exemple:
    - analysis_type='summary' → résumé global
    - analysis_type='thematic_clusters' → clusters thématiques
    - analysis_type='collaboration_network' → réseau collaboration
    """
    
    ANALYSIS_TYPES = [
        ('summary', 'Résumé global'),
        ('top_authors', 'Top auteurs'),
        ('thematic_clusters', 'Clusters thématiques'),
        ('collaboration_network', 'Réseau collaboration'),
        ('thematic_evolution', 'Évolution thématique'),
        ('cocitation', 'Co-citation'),
        ('coupling', 'Coupling bibliographique'),
        ('foundational_works', 'Publications fondatrices'),
        ('author_metrics', 'Métriques auteur'),
    ]
    
    analysis_type = models.CharField(
        max_length=50,
        choices=ANALYSIS_TYPES,
        db_index=True
    )
    
    # Paramètres utilisés pour l'analyse
    parameters = models.JSONField(default=dict)
    
    # Résultats complets (JSON depuis R)
    results = models.JSONField(default=dict)
    
    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'bibliometrix_analyses'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['analysis_type', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.get_analysis_type_display()} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
    
    @classmethod
    def get_latest(cls, analysis_type):
        """Récupérer l'analyse la plus récente d'un type donné"""
        try:
            return cls.objects.filter(
                analysis_type=analysis_type
            ).latest('created_at')
        except cls.DoesNotExist:
            return None


# ============================================================================
# 2. CACHE CHERCHEUR
# ============================================================================

class ResearcherBibliometricCache(models.Model):
    """
    Cache des métriques bibliométriques par chercheur
    
    Mis à jour lors de:
    - Ajout de nouvelles publications
    - Refresh explicite
    - Analyses globales Bibliometrix
    """
    
    # Chercheur
    researcher = models.OneToOneField(
        Researcher,
        on_delete=models.CASCADE,
        related_name='bibliometric_cache'
    )
    
    # === INDICATEURS PRINCIPAUX ===
    h_index = models.IntegerField(default=0, db_index=True)
    g_index = models.IntegerField(default=0)
    m_index = models.FloatField(default=0.0)
    
    # === PRODUCTION ===
    total_papers = models.IntegerField(default=0, db_index=True)
    total_citations = models.IntegerField(default=0)
    avg_citations = models.FloatField(default=0.0)
    
    # === DONNÉES TEMPORELLES ===
    yearly_output = models.JSONField(
        default=dict,
        help_text="Distribution des publications par année"
    )
    yearly_citations = models.JSONField(
        default=dict,
        help_text="Citations par année"
    )
    
    # === ANALYSES ===
    top_keywords = models.JSONField(
        default=list,
        help_text="Top 10 mots-clés"
    )
    top_journals = models.JSONField(
        default=list,
        help_text="Top 10 revues"
    )
    collaboration_network = models.JSONField(
        default=dict,
        help_text="Données réseau collaboration"
    )
    
    # === MÉTADONNÉES TEMPORELLES ===
    first_publication_year = models.IntegerField(null=True, blank=True)
    last_publication_year = models.IntegerField(null=True, blank=True)
    years_active = models.IntegerField(default=0)
    
    # === TIMESTAMPS ===
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'bibliometric_cache'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['h_index', '-total_papers']),
            models.Index(fields=['updated_at']),
        ]
    
    def __str__(self):
        return f"{self.researcher.user.username} (H={self.h_index}, Papers={self.total_papers})"
    
    def is_fresh(self, hours=24):
        """Vérifier si le cache est à jour (< N heures)"""
        return self.updated_at > timezone.now() - timedelta(hours=hours)
    
    @property
    def needs_refresh(self):
        """Le cache a-t-il besoin d'être rafraîchi?"""
        return not self.is_fresh(hours=24)
    
    def mark_stale(self):
        """Marquer le cache comme obsolète"""
        self.updated_at = timezone.now() - timedelta(hours=25)
        self.save(update_fields=['updated_at'])


# ============================================================================
# 3. HISTORIQUE DES ANALYSES (Optionnel - pour tracking)
# ============================================================================

class BibliometrixAnalysisHistory(models.Model):
    """
    Historique des analyses pour chaque chercheur
    Permet de voir l'évolution du H-index, etc.
    """
    
    researcher = models.ForeignKey(
        Researcher,
        on_delete=models.CASCADE,
        related_name='bibliometric_history'
    )
    
    # Snapshot des métriques à une date donnée
    h_index = models.IntegerField()
    total_papers = models.IntegerField()
    total_citations = models.IntegerField()
    avg_citations = models.FloatField()
    
    analysis_date = models.DateField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'bibliometric_history'
        ordering = ['-analysis_date']
        unique_together = ['researcher', 'analysis_date']
    
    def __str__(self):
        return f"{self.researcher.user.username} - {self.analysis_date} (H={self.h_index})"
    
    @classmethod
    def record_snapshot(cls, researcher, cache):
        """Enregistrer un snapshot du cache"""
        cls.objects.get_or_create(
            researcher=researcher,
            analysis_date=timezone.now().date(),
            defaults={
                'h_index': cache.h_index,
                'total_papers': cache.total_papers,
                'total_citations': cache.total_citations,
                'avg_citations': cache.avg_citations,
            }
        )