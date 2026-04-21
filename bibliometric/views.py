#!/usr/bin/env python3
# bibliometric/views.py - VERSION CORRIGÉE ET COMPLÈTE

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import models
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
import json
import logging

from .models import BibliometrixAnalysis, ResearcherBibliometricCache
from users.models import Researcher
from coAuthor.models import CoAuthor
from keywords.models import Keyword
from publication.models import Publication

logger = logging.getLogger(__name__)

# ============================================================================
# 1. ENDPOINTS GLOBAUX (Dashboard)
# ============================================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def bibliometrix_summary(request):
    """
    GET /api/bibliometrix/summary/
    Retourne le résumé global de l'analyse Bibliometrix
    """
    try:
        # Récupérer l'analyse la plus récente
        analysis = BibliometrixAnalysis.objects.filter(
            analysis_type='summary'
        ).latest('created_at')
        
        return Response({
            'success': True,
            'analysis_type': 'summary',
            'data': analysis.results,
            'created_at': analysis.created_at.isoformat()
        })
    except BibliometrixAnalysis.DoesNotExist:
        logger.warning("Aucune analyse summary trouvée")
        return Response(
            {'error': 'Aucune analyse trouvée. Lancez d\'abord Bibliometrix.'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def bibliometrix_top_authors(request):
    """
    GET /api/bibliometrix/top-authors/?n=20
    Retourne le top N auteurs
    """
    n = int(request.query_params.get('n', 20))
    
    try:
        analysis = BibliometrixAnalysis.objects.filter(
            analysis_type='top_authors'
        ).latest('created_at')
        
        # Limiter à N auteurs
        top_authors = analysis.results[:n] if isinstance(analysis.results, list) else []
        
        return Response({
            'success': True,
            'count': len(top_authors),
            'data': top_authors,
            'created_at': analysis.created_at.isoformat()
        })
    except BibliometrixAnalysis.DoesNotExist:
        return Response(
            {'error': 'Aucune analyse trouvée'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def bibliometrix_thematic_clusters(request):
    """
    GET /api/bibliometrix/thematic-clusters/
    Retourne les clusters thématiques
    """
    try:
        analysis = BibliometrixAnalysis.objects.filter(
            analysis_type='thematic_clusters'
        ).latest('created_at')
        
        return Response({
            'success': True,
            'analysis_type': 'thematic_clusters',
            'data': analysis.results,
            'created_at': analysis.created_at.isoformat()
        })
    except BibliometrixAnalysis.DoesNotExist:
        return Response(
            {'error': 'Aucune analyse trouvée'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def bibliometrix_collaboration_network(request):
    """
    GET /api/bibliometrix/collaboration-network/
    Retourne le réseau de collaboration
    """
    try:
        # Essayer d'obtenir les données réseau
        analysis = BibliometrixAnalysis.objects.filter(
            analysis_type='collaboration_network'
        ).latest('created_at')
        
        return Response({
            'success': True,
            'analysis_type': 'collaboration_network',
            'data': analysis.results,
            'created_at': analysis.created_at.isoformat()
        })
    except BibliometrixAnalysis.DoesNotExist:
        return Response(
            {'error': 'Aucune analyse trouvée'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bibliometrix_all_analyses(request):
    """
    GET /api/bibliometrix/all-analyses/
    Retourne la liste de toutes les analyses disponibles
    """
    analyses = BibliometrixAnalysis.objects.all().values(
        'id', 'analysis_type', 'created_at'
    ).order_by('-created_at')
    
    return Response({
        'success': True,
        'count': len(list(analyses)),
        'analyses': list(analyses)
    })


# ============================================================================
# 2. ENDPOINTS PAR CHERCHEUR
# ============================================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def researcher_bibliometric(request, researcher_id):
    """
    GET /api/bibliometrix/researcher/<id>/
    Retourne les métriques bibliométriques d'un chercheur
    """
    try:
        researcher = get_object_or_404(Researcher, id=researcher_id)
        
        # Récupérer ou créer le cache
        cache, created = ResearcherBibliometricCache.objects.get_or_create(
            researcher=researcher
        )
        
        # Si cache vide ou trop vieux, mettre à jour
        if cache.total_papers == 0 or not cache.is_fresh():
            update_researcher_cache(researcher, cache)
        
        # Récupérer les publications du chercheur
        coauthors = CoAuthor.objects.filter(
            linked_user=researcher.user
        ).select_related('publication', 'publication__journal')
        
        # Construire liste publications
        publications = []
        for ca in coauthors:
            pub = ca.publication
            publications.append({
                'id': pub.id,
                'title': pub.title[:100],  # Limiter la longueur
                'year': pub.publication_year,
                'citations': pub.citation_count or 0,
                'journal': pub.journal.name if pub.journal else 'Unknown',
                'doi': pub.doi,
            })
        
        return Response({
            'success': True,
            'researcher': {
                'id': researcher.id,
                'username': researcher.user.username,
                'name': f"{researcher.user.first_name} {researcher.user.last_name}".strip(),
                'orcid': researcher.orcid,
            },
            'metrics': {
                'h_index': cache.h_index,
                'g_index': cache.g_index,
                'm_index': cache.m_index,
                'total_papers': cache.total_papers,
                'total_citations': cache.total_citations,
                'avg_citations_per_paper': cache.avg_citations,
            },
            'temporal': {
                'first_publication_year': cache.first_publication_year,
                'last_publication_year': cache.last_publication_year,
                'years_active': cache.years_active,
                'yearly_output': cache.yearly_output,
            },
            'analysis': {
                'top_keywords': cache.top_keywords,
                'top_journals': cache.top_journals,
            },
            'publications': publications[:20],  # Limiter à 20
            'last_updated': cache.updated_at.isoformat(),
        })
        
    except Researcher.DoesNotExist:
        return Response(
            {'error': 'Chercheur non trouvé'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Erreur researcher_bibliometric: {e}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def researcher_bibliometric_by_name(request, name):
    """
    GET /api/bibliometrix/researcher/name/<name>/
    Recherche un chercheur par nom et retourne ses métriques
    """
    researchers = Researcher.objects.filter(
        models.Q(user__username__icontains=name) |
        models.Q(user__first_name__icontains=name) |
        models.Q(user__last_name__icontains=name)
    )
    
    if not researchers.exists():
        return Response(
            {'error': f'Aucun chercheur trouvé pour "{name}"'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    researcher = researchers.first()
    return researcher_bibliometric(request, researcher.id)


@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_researcher_cache(request, researcher_id):
    """
    POST /api/bibliometrix/researcher/<id>/refresh/
    Force le rafraîchissement du cache d'un chercheur
    """
    try:
        researcher = get_object_or_404(Researcher, id=researcher_id)
        cache, _ = ResearcherBibliometricCache.objects.get_or_create(
            researcher=researcher
        )
        
        # Forcer la mise à jour
        update_researcher_cache(researcher, cache, force=True)
        
        return Response({
            'success': True,
            'message': f'Cache mis à jour pour {researcher.user.username}',
            'metrics': {
                'h_index': cache.h_index,
                'total_papers': cache.total_papers,
                'total_citations': cache.total_citations,
            }
        })
    except Exception as e:
        logger.error(f"Erreur refresh_researcher_cache: {e}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ============================================================================
# 3. ENDPOINTS DE CLASSEMENT
# ============================================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def researcher_ranking(request):
    """
    GET /api/bibliometrix/ranking/?by=h_index&limit=20
    Classement des chercheurs par métrique
    """
    by = request.query_params.get('by', 'h_index')
    limit = int(request.query_params.get('limit', 20))
    
    allowed_fields = ['h_index', 'total_papers', 'total_citations', 'avg_citations']
    
    if by not in allowed_fields:
        return Response(
            {'error': f'by doit être parmi {allowed_fields}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Construire l'ordre
    order_by = f'-{by}'
    
    caches = ResearcherBibliometricCache.objects.select_related(
        'researcher__user'
    ).filter(total_papers__gt=0).order_by(order_by)[:limit]
    
    ranking = []
    for idx, cache in enumerate(caches, 1):
        user = cache.researcher.user
        ranking.append({
            'rank': idx,
            'researcher_id': cache.researcher.id,
            'name': f"{user.first_name} {user.last_name}".strip() or user.username,
            'username': user.username,
            'orcid': cache.researcher.orcid,
            'h_index': cache.h_index,
            'total_papers': cache.total_papers,
            'total_citations': cache.total_citations,
            'avg_citations': round(cache.avg_citations, 2),
        })
    
    return Response({
        'success': True,
        'ranking_by': by,
        'total_researchers': ResearcherBibliometricCache.objects.filter(total_papers__gt=0).count(),
        'ranking': ranking,
    })


# ============================================================================
# 4. DASHBOARD GLOBAL
# ============================================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def bibliometrix_dashboard(request):
    """
    GET /api/bibliometrix/dashboard/
    Dashboard global avec toutes les statistiques
    """
    # Statistiques depuis caches
    caches = ResearcherBibliometricCache.objects.filter(total_papers__gt=0)
    
    total_researchers = caches.count()
    avg_h_index = caches.aggregate(models.Avg('h_index'))['h_index__avg'] or 0
    total_publications = caches.aggregate(models.Sum('total_papers'))['total_papers__sum'] or 0
    total_citations = caches.aggregate(models.Sum('total_citations'))['total_citations__sum'] or 0
    
    # Top 10 chercheurs
    top_researchers = caches.select_related('researcher__user').order_by('-h_index')[:10]
    top_list = []
    for cache in top_researchers:
        user = cache.researcher.user
        top_list.append({
            'id': cache.researcher.id,
            'name': f"{user.first_name} {user.last_name}".strip() or user.username,
            'h_index': cache.h_index,
            'papers': cache.total_papers,
            'citations': cache.total_citations,
        })
    
    # Récupérer l'analyse R summary si disponible
    r_summary = None
    try:
        analysis = BibliometrixAnalysis.objects.filter(
            analysis_type='summary'
        ).latest('created_at')
        r_summary = analysis.results
    except BibliometrixAnalysis.DoesNotExist:
        pass
    
    return Response({
        'success': True,
        'global_stats': {
            'total_researchers': total_researchers,
            'total_publications': int(total_publications),
            'total_citations': int(total_citations),
            'average_h_index': round(avg_h_index, 1),
        },
        'top_researchers': top_list,
        'r_analysis': r_summary,
        'last_updated': caches.aggregate(models.Max('updated_at'))['updated_at__max'],
    })


# ============================================================================
# 5. FONCTIONS UTILITAIRES
# ============================================================================

def update_researcher_cache(researcher, cache, force=False):
    """
    Met à jour le cache bibliométrique d'un chercheur
    """
    try:
        # Récupérer toutes les publications du chercheur
        coauthors = CoAuthor.objects.filter(
            linked_user=researcher.user
        ).select_related('publication', 'publication__journal')
        
        if not coauthors.exists():
            cache.total_papers = 0
            cache.save()
            return
        
        # === MÉTRIQUES DE BASE ===
        total_papers = coauthors.count()
        total_citations = sum(ca.publication.citation_count or 0 for ca in coauthors)
        avg_citations = round(total_citations / total_papers, 2) if total_papers > 0 else 0
        
        # === CALCUL H-INDEX ===
        citations = sorted(
            [ca.publication.citation_count or 0 for ca in coauthors],
            reverse=True
        )
        h_index = 0
        for i, c in enumerate(citations, 1):
            if c >= i:
                h_index = i
            else:
                break
        
        # === CALCUL G-INDEX ===
        g_index = h_index
        total = 0
        for i, c in enumerate(citations, 1):
            total += c
            if total >= i * i:
                g_index = i
        
        # === PUBLICATIONS PAR ANNÉE ===
        yearly_output = {}
        years_list = []
        for ca in coauthors:
            year = ca.publication.publication_year
            if year:
                yearly_output[str(year)] = yearly_output.get(str(year), 0) + 1
                years_list.append(year)
        
        # === ANNÉES D'ACTIVITÉ ===
        if years_list:
            first_year = min(years_list)
            last_year = max(years_list)
            years_active = last_year - first_year + 1
        else:
            first_year = None
            last_year = None
            years_active = 0
        
        # === M-INDEX ===
        m_index = round(h_index / years_active, 2) if years_active > 0 else 0
        
        # === TOP KEYWORDS ===
        publication_ids = [ca.publication.id for ca in coauthors]
        keywords = Keyword.objects.filter(
            publications__id__in=publication_ids
        ).values('label').annotate(
            count=models.Count('id')
        ).order_by('-count')[:10]
        
        top_keywords = [{'keyword': k['label'], 'count': k['count']} for k in keywords]
        
        # === TOP JOURNALS ===
        journal_counts = {}
        for ca in coauthors:
            if ca.publication.journal:
                journal_name = ca.publication.journal.name
                journal_counts[journal_name] = journal_counts.get(journal_name, 0) + 1
        
        top_journals = [
            {'journal': name, 'count': count}
            for name, count in sorted(journal_counts.items(), key=lambda x: -x[1])[:10]
        ]
        
        # === METTRE À JOUR LE CACHE ===
        cache.h_index = h_index
        cache.g_index = g_index
        cache.m_index = m_index
        cache.total_papers = total_papers
        cache.total_citations = total_citations
        cache.avg_citations = avg_citations
        cache.yearly_output = yearly_output
        cache.top_keywords = top_keywords
        cache.top_journals = top_journals
        cache.first_publication_year = first_year
        cache.last_publication_year = last_year
        cache.years_active = years_active
        cache.save()
        
        logger.info(f"Cache mis à jour pour {researcher.user.username} (H={h_index}, Papers={total_papers})")
        
    except Exception as e:
        logger.error(f"Erreur update_researcher_cache: {e}")
        raise