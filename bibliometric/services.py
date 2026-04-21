# bibliometric/services.py
import subprocess
import json
import tempfile
import os
from pathlib import Path
from django.conf import settings
from citation.models import *
from users.models import Researcher
from coAuthor.models import CoAuthor
from .models import ResearcherBibliometricCache

class BibliometricRService:
    
    @classmethod
    def analyze_and_cache(cls, researcher_id, force_refresh=False):
        try:
            researcher = Researcher.objects.get(id=researcher_id)
            cache, created = ResearcherBibliometricCache.objects.get_or_create(researcher=researcher)
            
            if not force_refresh and cache.is_fresh():
                return {'success': True, 'from_cache': True}
            
            # Récupérer les publications du chercheur
            coauthors = CoAuthor.objects.filter(
                linked_user=researcher.user
            ).select_related('publication')
            
            if not coauthors.exists():
                return {'success': False, 'error': 'Aucune publication'}
            
            # Calculer les métriques
            total_papers = coauthors.count()
            total_citations = sum(ca.publication.citation_count or 0 for ca in coauthors)
            
            # Calculer H-index
            citations = sorted([ca.publication.citation_count or 0 for ca in coauthors], reverse=True)
            h_index = 0
            for i, c in enumerate(citations, 1):
                if c >= i:
                    h_index = i
                else:
                    break
            
            # Publications par année
            yearly_output = {}
            for ca in coauthors:
                year = ca.publication.publication_year
                if year:
                    yearly_output[str(year)] = yearly_output.get(str(year), 0) + 1
            
            # Top keywords
            from keywords.models import Keyword
            keywords = Keyword.objects.filter(
                publications__in=[ca.publication for ca in coauthors]
            ).values('label').annotate(count=models.Count('id')).order_by('-count')[:10]
            
            top_keywords = [{'keyword': k['label'], 'count': k['count']} for k in keywords]
            
            # Mettre à jour le cache
            cache.h_index = h_index
            cache.g_index = h_index  # Approximation
            cache.total_papers = total_papers
            cache.total_citations = total_citations
            cache.avg_citations = round(total_citations / total_papers, 2) if total_papers > 0 else 0
            cache.yearly_output = yearly_output
            cache.top_keywords = top_keywords
            cache.save()
            
            return {'success': True, 'from_cache': False}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}