"""
metrics_functions.py - VERSION OPTIMISÉE
"""

import requests
import time
import logging
from django.db import models
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)
BASE_URL = "https://api.openalex.org"
HEADERS = {"User-Agent": "mailto:ridaelaidate7@gmail.com"}


# ─────────────────────────────────────────────────────────────────────────────
# 📊 ALTMETRIC SCORE (optimisé)
# ─────────────────────────────────────────────────────────────────────────────

def compute_altmetric_scores(publications_map: dict):
    """Calcule Altmetric Score en une seule requête SQL"""
    from coAuthor.models import CoAuthor
    from publication.models import Publication
    
    pubs = list(publications_map.values())
    if not pubs:
        return
    
    pub_ids = [p.id for p in pubs]
    
    # Une seule requête pour les coauthors
    coauthor_counts = dict(
        CoAuthor.objects
        .filter(publication_id__in=pub_ids)
        .values_list("publication_id")
        .annotate(count=models.Count("publication_id"))
    )
    
    # Une seule requête pour les keywords
    through = Publication.keywords.through
    keyword_counts = dict(
        through.objects
        .filter(publication_id__in=pub_ids)
        .values_list("publication_id")
        .annotate(count=models.Count("publication_id"))
    )
    
    to_update = []
    for pub in pubs:
        citations = pub.citation_count or 0
        keywords = keyword_counts.get(pub.id, 0)
        coauthors = coauthor_counts.get(pub.id, 0)
        
        score = citations * 0.6 + keywords * 0.2 + coauthors * 0.2
        pub.altmetric_score = round(score, 2)
        to_update.append(pub)
    
    if to_update:
        Publication.objects.bulk_update(to_update, ["altmetric_score"])
        print(f"  📊 Altmetric: {len(to_update)} pubs mis à jour")


# ─────────────────────────────────────────────────────────────────────────────
# 📰 IMPACT FACTOR - VERSION BATCH OPTIMISÉE
# ─────────────────────────────────────────────────────────────────────────────

def fetch_journal_impact_factors_batch(journals_map: dict = None, batch_size: int = 50) -> int:
    """
    ✅ Récupère les Impact Factors en BATCH (beaucoup plus rapide !)
    
    Utilise le filter OR d'OpenAlex pour traiter plusieurs journaux par requête
    """
    from journal.models import Journal
    
    # Récupérer les journaux uniques (sans doublons)
    if journals_map:
        # Extraire les journaux uniques par ISSN
        unique_journals = {}
        for journal in journals_map.values():
            if journal and journal.issn and journal.issn not in unique_journals:
                unique_journals[journal.issn] = journal
        journals_list = list(unique_journals.values())
    else:
        journals_list = list(Journal.objects.filter(
            issn__isnull=False
        ).exclude(issn="").distinct())
    
    if not journals_list:
        print(f"  ⚠️  Aucun journal avec ISSN")
        return 0
    
    print(f"  📰 Mise à jour IF pour {len(journals_list)} journaux uniques...")
    
    # Traiter par lots d'ISSN
    updated_count = 0
    to_update = []
    
    for i in range(0, len(journals_list), batch_size):
        batch = journals_list[i:i+batch_size]
        issns = [j.issn for j in batch if j.issn]
        
        if not issns:
            continue
        
        try:
            # Requête BATCH : filter issn:1234-5678|8765-4321|...
            issn_filter = "|".join(issns[:25])  # Max 25 par requête
            response = requests.get(
                f"{BASE_URL}/sources",
                params={
                    "filter": f"issn:{issn_filter}",
                    "select": "id,issn,issn_l,summary_stats",
                    "per_page": 25,
                },
                headers=HEADERS,
                timeout=30
            )
            response.raise_for_status()
            results = response.json().get("results", [])
            
            # Créer un mapping ISSN -> données
            issn_data = {}
            for source in results:
                for issn in source.get("issn", []):
                    if issn:
                        issn_data[issn] = source.get("summary_stats", {})
            
            # Mettre à jour les journaux
            for journal in batch:
                if journal.issn in issn_data:
                    summary = issn_data[journal.issn]
                    cite_score = summary.get("2yr_mean_citedness", 0) or 0
                    if cite_score:
                        journal.impact_factor = round(float(cite_score), 3)
                        to_update.append(journal)
                        updated_count += 1
            
            print(f"     Batch {i//batch_size + 1}: {len(batch)} traités, {updated_count} trouvés")
            time.sleep(0.2)  # Pause légère entre les batches
            
        except Exception as e:
            logger.error(f"Erreur batch IF: {e}")
            continue
    
    # Mise à jour en masse
    if to_update:
        Journal.objects.bulk_update(to_update, ["impact_factor"])
        print(f"\n  ✅ {updated_count} journaux mis à jour")
    
    return updated_count


# Garder l'ancienne fonction pour compatibilité
def fetch_journal_impact_factors(journals_map: dict = None) -> int:
    """Wrapper pour la version batch"""
    return fetch_journal_impact_factors_batch(journals_map)