# data_pipeline/bibliometrix_indicators.py
"""
📊 INDICATEURS BIBLIOMETRIQUES POUR PYTHON/DJANGO
Calcule les mêmes indicateurs que Bibliometrix (production, impact, collaboration)
"""

from django.db import models
from django.db.models import Count, Sum, Avg, Q, F
from django.db.models.functions import ExtractYear
from collections import Counter
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional


class BibliometricIndicators:
    """
    Calcule les indicateurs bibliométriques pour différents niveaux d'agrégation
    """
    
    def __init__(self, publications_queryset):
        """
        publications_queryset: QuerySet de publications
        """
        self.pubs = publications_queryset
        self.df = self._to_dataframe()
    
    def _to_dataframe(self):
        """Convertit les publications en DataFrame pandas"""
        data = []
        for pub in self.pubs.select_related('journal', 'institution').prefetch_related('reseachers', 'coauthors'):
            # Récupérer les auteurs
            authors = [ca.author_name for ca in pub.coauthors.all().order_by('author_order')]
            
            data.append({
                'id': pub.id,
                'title': pub.title,
                'year': pub.publication_year,
                'citations': pub.citation_count or 0,
                'journal': pub.journal.name if pub.journal else 'Unknown',
                'institution': pub.institution.name if pub.institution else 'Unknown',
                'authors': ';'.join(authors),
                'author_count': len(authors),
                'doi': pub.doi,
            })
        
        return pd.DataFrame(data)
    
    # ═══════════════════════════════════════════════════════════════════════
    # 📊 INDICATEURS DE PRODUCTION
    # ═══════════════════════════════════════════════════════════════════════
    
    def total_publications(self) -> int:
        """Nombre total de publications"""
        return len(self.pubs)
    
    def publications_by_year(self) -> Dict[int, int]:
        """Publications par année"""
        return dict(self.pubs.values_list('publication_year', 'id').annotate(count=Count('id')))
    
    def annual_growth_rate(self) -> float:
        """Taux de croissance annuel moyen"""
        yearly_counts = self.publications_by_year()
        years = sorted(yearly_counts.keys())
        
        if len(years) < 2:
            return 0.0
        
        first_year = years[0]
        last_year = years[-1]
        first_count = yearly_counts[first_year]
        last_count = yearly_counts[last_year]
        
        n_years = last_year - first_year
        if n_years == 0 or first_count == 0:
            return 0.0
        
        growth_rate = ((last_count / first_count) ** (1 / n_years) - 1) * 100
        return round(growth_rate, 2)
    
    def top_producers(self, by='author', limit=20) -> List[Dict]:
        """Top producteurs (par auteur, institution, journal)"""
        if by == 'author':
            # Compter par auteur (via CoAuthor)
            from coAuthor.models import CoAuthor
            top = CoAuthor.objects.filter(
                publication__in=self.pubs
            ).values('author_name').annotate(
                count=Count('publication', distinct=True)
            ).order_by('-count')[:limit]
            
            return [{'name': t['author_name'], 'count': t['count']} for t in top]
        
        elif by == 'institution':
            top = self.pubs.values('institution__name').annotate(
                count=Count('id')
            ).order_by('-count')[:limit]
            return [{'name': t['institution__name'] or 'Unknown', 'count': t['count']} for t in top]
        
        elif by == 'journal':
            top = self.pubs.values('journal__name').annotate(
                count=Count('id')
            ).order_by('-count')[:limit]
            return [{'name': t['journal__name'] or 'Unknown', 'count': t['count']} for t in top]
        
        return []
    
    # ═══════════════════════════════════════════════════════════════════════
    # 📈 INDICATEURS D'IMPACT
    # ═══════════════════════════════════════════════════════════════════════
    
    def total_citations(self) -> int:
        """Nombre total de citations"""
        return self.pubs.aggregate(total=Sum('citation_count'))['total'] or 0
    
    def avg_citations_per_paper(self) -> float:
        """Moyenne des citations par article"""
        total = self.total_citations()
        count = self.total_publications()
        return round(total / count, 2) if count > 0 else 0
    
    def citation_distribution(self, bins=[0, 5, 10, 20, 50, 100, 500, 1000]) -> Dict:
        """Distribution des citations"""
        citations = list(self.pubs.values_list('citation_count', flat=True))
        hist, _ = np.histogram(citations, bins=bins)
        return {f"{bins[i]}-{bins[i+1]}": int(hist[i]) for i in range(len(hist))}
    
    def h_index(self, author_name: str = None) -> int:
        """Calcul du H-index (global ou par auteur)"""
        if author_name:
            # H-index d'un auteur spécifique
            from coAuthor.models import CoAuthor
            citations = CoAuthor.objects.filter(
                author_name=author_name,
                publication__in=self.pubs
            ).values_list('publication__citation_count', flat=True)
        else:
            # H-index global (tous articles triés par citations)
            citations = list(self.pubs.values_list('citation_count', flat=True))
        
        citations = sorted([c for c in citations if c > 0], reverse=True)
        
        h = 0
        for i, c in enumerate(citations, 1):
            if c >= i:
                h = i
            else:
                break
        return h
    
    def g_index(self) -> int:
        """Calcul du G-index (prend en compte la distribution des citations)"""
        citations = sorted([c for c in self.pubs.values_list('citation_count', flat=True) if c > 0], reverse=True)
        
        g = 0
        total_citations = 0
        for i, c in enumerate(citations, 1):
            total_citations += c
            if total_citations >= i**2:
                g = i
            else:
                break
        return g
    
    def m_index(self, author_name: str = None) -> float:
        """M-index = h-index / nombre d'années depuis première publication"""
        h = self.h_index(author_name)
        
        # Trouver la première publication
        first_pub_year = self.pubs.aggregate(first=models.Min('publication_year'))['first']
        current_year = 2026  # ou datetime.now().year
        
        if first_pub_year and current_year > first_pub_year:
            years_active = current_year - first_pub_year
            return round(h / years_active, 2) if years_active > 0 else 0
        return 0
    
    def most_cited_papers(self, limit=20) -> List[Dict]:
        """Articles les plus cités"""
        top = self.pubs.order_by('-citation_count')[:limit]
        return [{
            'title': p.title[:100],
            'year': p.publication_year,
            'citations': p.citation_count or 0,
            'journal': p.journal.name if p.journal else 'Unknown',
            'doi': p.doi
        } for p in top]
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🤝 INDICATEURS DE COLLABORATION
    # ═══════════════════════════════════════════════════════════════════════
    
    def avg_coauthors_per_paper(self) -> float:
        """Nombre moyen de co-auteurs par article"""
        from coAuthor.models import CoAuthor
        total_coauthors = CoAuthor.objects.filter(publication__in=self.pubs).count()
        pub_count = self.total_publications()
        return round(total_coauthors / pub_count, 2) if pub_count > 0 else 0
    
    def single_author_papers(self) -> int:
        """Nombre d'articles en solo"""
        from coAuthor.models import CoAuthor
        # Trouver les publications avec un seul co-auteur
        single_authored = CoAuthor.objects.filter(
            publication__in=self.pubs
        ).values('publication_id').annotate(
            author_count=Count('id')
        ).filter(author_count=1).values_list('publication_id', flat=True)
        
        return len(single_authored)
    
    def collaboration_network(self, limit=50) -> Dict:
        """Réseau de collaboration (co-auteurs)"""
        from coAuthor.models import CoAuthor
        from collections import defaultdict
        
        edges = []
        nodes = set()
        
        # Pour chaque publication, créer des liens entre co-auteurs
        for pub in self.pubs.prefetch_related('coauthors'):
            authors = list(pub.coauthors.order_by('author_order').values_list('author_name', flat=True))
            
            for i, a1 in enumerate(authors):
                nodes.add(a1)
                for a2 in authors[i+1:]:
                    nodes.add(a2)
                    edges.append({'source': a1, 'target': a2, 'weight': 1})
        
        # Agréger les poids
        edge_weights = defaultdict(int)
        for edge in edges:
            key = tuple(sorted([edge['source'], edge['target']]))
            edge_weights[key] += edge['weight']
        
        # Formater pour visualisation
        formatted_edges = [
            {'source': s, 'target': t, 'weight': w}
            for (s, t), w in sorted(edge_weights.items(), key=lambda x: -x[1])[:limit]
        ]
        
        return {
            'nodes': list(nodes)[:limit*2],
            'edges': formatted_edges
        }
    
    def international_collaboration_rate(self) -> float:
        """Taux de collaboration internationale"""
        # À implémenter avec les affiliations des institutions
        # Pour l'instant, retourne 0
        return 0.0
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🏷️ ANALYSE THÉMATIQUE
    # ═══════════════════════════════════════════════════════════════════════
    
    def keyword_analysis(self, limit=20) -> List[Dict]:
        """Analyse des mots-clés les plus fréquents"""
        from keywords.models import Keyword
        
        keywords = Keyword.objects.filter(
            publication__in=self.pubs
        ).values('label').annotate(
            count=Count('id')
        ).order_by('-count')[:limit]
        
        return [{'keyword': k['label'], 'count': k['count']} for k in keywords]
    
    def keyword_trends(self, keywords_list: List[str]) -> Dict[int, Dict[str, int]]:
        """Évolution temporelle de mots-clés spécifiques"""
        trends = {}
        
        for pub in self.pubs.prefetch_related('keywords'):
            year = pub.publication_year
            if year not in trends:
                trends[year] = {kw: 0 for kw in keywords_list}
            
            for kw in pub.keywords.all():
                if kw.label in keywords_list:
                    trends[year][kw.label] += 1
        
        return trends


# ═══════════════════════════════════════════════════════════════════════════
# 🎯 CALCUL PAR NIVEAU D'AGRÉGATION
# ═══════════════════════════════════════════════════════════════════════════

def calculate_indicators_for_entity(entity_type: str, entity_id: int, start_year: int = None, end_year: int = None):
    """
    Calcule les indicateurs pour une entité spécifique
    
    entity_type: 'researcher', 'team', 'laboratory', 'institution'
    entity_id: ID de l'entité
    """
    from publication.models import Publication
    
    # Construire le queryset selon le type d'entité
    if entity_type == 'researcher':
        from users.models import Researcher
        researcher = Researcher.objects.get(id=entity_id)
        publications = researcher.publications.all()
    
    elif entity_type == 'team':
        from team.models import Team
        team = Team.objects.get(id=entity_id)
        researchers = team.members.all()
        publications = Publication.objects.filter(reseachers__in=researchers).distinct()
    
    elif entity_type == 'laboratory':
        from laboratory.models import Laboratory
        lab = Laboratory.objects.get(id=entity_id)
        researchers = lab.members.all()
        publications = Publication.objects.filter(reseachers__in=researchers).distinct()
    
    elif entity_type == 'institution':
        from institution.models import Institution
        inst = Institution.objects.get(id=entity_id)
        publications = Publication.objects.filter(institution=inst)
    
    else:
        raise ValueError(f"Type d'entité inconnu: {entity_type}")
    
    # Filtrer par année
    if start_year:
        publications = publications.filter(publication_year__gte=start_year)
    if end_year:
        publications = publications.filter(publication_year__lte=end_year)
    
    # Calculer les indicateurs
    indicators = BibliometricIndicators(publications)
    
    return {
        'entity_type': entity_type,
        'entity_id': entity_id,
        'production': {
            'total_publications': indicators.total_publications(),
            'publications_by_year': indicators.publications_by_year(),
            'annual_growth_rate': indicators.annual_growth_rate(),
            'top_journals': indicators.top_producers(by='journal', limit=10),
        },
        'impact': {
            'total_citations': indicators.total_citations(),
            'avg_citations_per_paper': indicators.avg_citations_per_paper(),
            'h_index': indicators.h_index(),
            'g_index': indicators.g_index(),
            'most_cited_papers': indicators.most_cited_papers(limit=10),
        },
        'collaboration': {
            'avg_coauthors_per_paper': indicators.avg_coauthors_per_paper(),
            'single_author_papers': indicators.single_author_papers(),
        },
        'thematic': {
            'top_keywords': indicators.keyword_analysis(limit=20),
        }
    }


def update_researcher_h_index(researcher_id: int) -> int:
    """
    Met à jour le H-index d'un chercheur et retourne la nouvelle valeur
    """
    from users.models import Researcher
    
    researcher = Researcher.objects.get(id=researcher_id)
    publications = researcher.publications.all()
    
    if not publications.exists():
        if researcher.h_index != 0:
            researcher.h_index = 0
            researcher.save(update_fields=['h_index'])
        return 0
    
    # ✅ CORRECTION : Utiliser citation_count directement
    citation_counts = []
    for pub in publications:
        citations = pub.citation_count or 0
        citation_counts.append(citations)
    
    # Trier par ordre décroissant
    citation_counts.sort(reverse=True)
    
    # Calculer le H-index
    h = 0
    for i, c in enumerate(citation_counts, 1):
        if c >= i:
            h = i
        else:
            break
    
    # Mettre à jour dans la base
    if researcher.h_index != h:
        researcher.h_index = h
        researcher.save(update_fields=['h_index'])
        print(f"  📊 H-index mis à jour pour {researcher.user.username}: {h}")
    else:
        print(f"  📊 H-index pour {researcher.user.username}: {h} (inchangé)")
    
    return h


def update_all_researchers_h_index():
    """Met à jour le H-index de tous les chercheurs"""
    from users.models import Researcher
    
    updated = 0
    total = Researcher.objects.count()
    
    for i, researcher in enumerate(Researcher.objects.all(), 1):
        h = update_researcher_h_index(researcher.id)
        if h > 0:
            updated += 1
        if i % 10 == 0:
            print(f"  Progression: {i}/{total} chercheurs traités")
    
    return {'total_researchers': total, 'updated': updated}


def update_all_researchers_h_index():
    """Met à jour le H-index de tous les chercheurs"""
    from users.models import Researcher
    from django.db import transaction
    
    updated = 0
    for researcher in Researcher.objects.all():
        h = update_researcher_h_index(researcher.id)
        if h > 0:
            updated += 1
    
    return {'total_researchers': Researcher.objects.count(), 'updated': updated}