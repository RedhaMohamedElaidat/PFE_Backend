"""
services.py — Toutes les fonctions de données pour le chatbot
Singulier → 1 résultat | Pluriel → liste
"""
from django.db.models import Sum, Count, Avg, Q


# ─── PUBLICATIONS ─────────────────────────────────────────────────────────────

def highest_cited_publications(limit=5):
    """Pluriel → liste des N publications les plus citées."""
    from publication.models import Publication
    pubs = Publication.objects.select_related('journal').order_by("-citation_count")[:limit]
    return [
        {
            "title":     p.title,
            "year":      p.publication_year,
            "citations": p.citation_count,
            "journal":   p.journal.name if p.journal else "-",
            "doi":       p.doi or "-",
        }
        for p in pubs
    ]


def best_publication():
    """Singulier → LA publication la plus citée uniquement."""
    from publication.models import Publication
    pub = Publication.objects.select_related('journal').order_by('-citation_count').first()
    if not pub:
        return None
    return {
        "title":     pub.title,
        "year":      pub.publication_year,
        "citations": pub.citation_count,
        "journal":   pub.journal.name if pub.journal else "-",
        "doi":       pub.doi or "-",
    }


def search_publications(query, limit=5):
    from publication.models import Publication
    pubs = Publication.objects.filter(
        Q(title__icontains=query) |
        Q(abstract__icontains=query)
    ).order_by("-citation_count")[:limit]
    return [
        {
            "title":     p.title,
            "year":      p.publication_year,
            "citations": p.citation_count,
            "journal":   p.journal.name if p.journal else "-",
        }
        for p in pubs
    ]


def publications_by_year(year):
    from publication.models import Publication
    pubs = Publication.objects.filter(
        publication_year=year
    ).order_by("-citation_count")
    return [
        {
            "title":     p.title,
            "citations": p.citation_count,
            "journal":   p.journal.name if p.journal else "-",
        }
        for p in pubs
    ]


def publications_by_journal(journal_name, limit=10):
    from publication.models import Publication
    pubs = Publication.objects.filter(
        journal__name__icontains=journal_name
    ).order_by("-citation_count")[:limit]
    return [
        {
            "title":     p.title,
            "year":      p.publication_year,
            "citations": p.citation_count,
        }
        for p in pubs
    ]


def recent_publications(limit=5):
    from publication.models import Publication
    pubs = Publication.objects.order_by("-publication_year", "-citation_count")[:limit]
    return [
        {
            "title":   p.title,
            "year":    p.publication_year,
            "journal": p.journal.name if p.journal else "-",
        }
        for p in pubs
    ]


def publication_detail(title_query):
    from publication.models import Publication
    pub = Publication.objects.filter(
        title__icontains=title_query
    ).select_related('journal').prefetch_related('keywords').first()
    if not pub:
        return None
    return {
        "title":     pub.title,
        "year":      pub.publication_year,
        "journal":   pub.journal.name if pub.journal else "-",
        "doi":       pub.doi or "-",
        "citations": pub.citation_count,
        "abstract":  pub.abstract[:300] + "..." if pub.abstract else "-",
        "keywords":  [kw.label for kw in pub.keywords.all()],
        "type":      pub.type,
    }


# ─── CHERCHEURS ───────────────────────────────────────────────────────────────

def top_researchers(limit=5):
    """Pluriel → liste des N meilleurs chercheurs."""
    from users.models import Researcher
    researchers = Researcher.objects.select_related('user').filter(
        user__is_active=True
    ).exclude(
        user__email__icontains="external.openalex"
    ).order_by("-h_index")[:limit]
    return [
        {
            "name":    r.user.get_full_name() or r.user.username,
            "h_index": r.h_index,
            "orcid":   r.orcid or "-",
            "field":   r.research_field or "-",
        }
        for r in researchers
    ]


def best_researcher():
    """Singulier → LE meilleur chercheur uniquement."""
    from users.models import Researcher
    researcher = Researcher.objects.select_related('user').filter(
        user__is_active=True
    ).exclude(
        user__email__icontains="external.openalex"
    ).order_by('-h_index').first()

    if not researcher:
        return None

    return {
        "name":           researcher.user.get_full_name() or researcher.user.username,
        "h_index":        researcher.h_index,
        "orcid":          researcher.orcid or "-",
        "research_field": researcher.research_field or "-",
    }


def researcher_publications(name_query):
    from users.models import Researcher
    from coAuthor.models import CoAuthor

    researcher = Researcher.objects.filter(
        Q(user__first_name__icontains=name_query) |
        Q(user__last_name__icontains=name_query)
    ).select_related('user').first()

    if not researcher:
        return None

    coauthorships = CoAuthor.objects.filter(
        author=researcher.user
    ).select_related('publication__journal').order_by(
        '-publication__publication_year'
    )

    return {
        "researcher": researcher.user.get_full_name(),
        "h_index":    researcher.h_index,
        "orcid":      researcher.orcid or "-",
        "publications": [
            {
                "title":     ca.publication.title,
                "year":      ca.publication.publication_year,
                "citations": ca.publication.citation_count,
                "journal":   ca.publication.journal.name if ca.publication.journal else "-",
                "order":     ca.author_order,
            }
            for ca in coauthorships
        ]
    }


def researcher_stats(name_query):
    from users.models import Researcher
    from coAuthor.models import CoAuthor
    from citation.models import Citation

    researcher = Researcher.objects.filter(
        Q(user__first_name__icontains=name_query) |
        Q(user__last_name__icontains=name_query)
    ).select_related('user').first()

    if not researcher:
        return None

    pub_ids = CoAuthor.objects.filter(
        author=researcher.user
    ).values_list('publication_id', flat=True)

    total_citations = Citation.objects.filter(
        cited_publication_id__in=pub_ids
    ).count()

    return {
        "name":               researcher.user.get_full_name(),
        "h_index":            researcher.h_index,
        "orcid":              researcher.orcid or "-",
        "total_publications": len(pub_ids),
        "total_citations":    total_citations,
        "research_field":     researcher.research_field or "-",
    }


# ─── CITATIONS ────────────────────────────────────────────────────────────────

def citation_stats():
    from citation.models import Citation
    from publication.models import Publication

    total   = Citation.objects.count()
    avg_cit = Publication.objects.aggregate(avg=Avg('citation_count'))['avg'] or 0
    max_pub = Publication.objects.order_by('-citation_count').first()

    return {
        "total_citation_links":      total,
        "average_citations_per_pub": round(avg_cit, 2),
        "most_cited_publication": {
            "title":     max_pub.title if max_pub else "-",
            "citations": max_pub.citation_count if max_pub else 0,
        }
    }


def citations_of_publication(title_query):
    from publication.models import Publication
    from citation.models import Citation

    pub = Publication.objects.filter(title__icontains=title_query).first()
    if not pub:
        return None

    incoming = Citation.objects.filter(
        cited_publication=pub
    ).select_related('citing_publication').order_by(
        '-citing_publication__publication_year'
    )

    return {
        "publication":     pub.title,
        "total_citations": pub.citation_count,
        "citing_works": [
            {
                "title": c.citing_publication.title,
                "year":  c.citing_publication.publication_year,
            }
            for c in incoming[:10]
        ]
    }


# ─── JOURNAUX ─────────────────────────────────────────────────────────────────

def top_journals(limit=5):
    """Pluriel → liste des N meilleurs journaux."""
    from journal.models import Journal

    journals = Journal.objects.annotate(
        pub_count=Count('publications'),
        total_cit=Sum('publications__citation_count')
    ).order_by('-total_cit')[:limit]

    return [
        {
            "name":            j.name,
            "issn":            j.issn or "-",
            "publications":    j.pub_count or 0,
            "total_citations": j.total_cit or 0,
            "impact_factor":   j.impact_factor or "-",
        }
        for j in journals
    ]


def best_journal():
    """Singulier → LE meilleur journal uniquement."""
    from journal.models import Journal

    journal = Journal.objects.annotate(
        pub_count=Count('publications'),
        total_cit=Sum('publications__citation_count')
    ).order_by('-total_cit').first()

    if not journal:
        return None

    return {
        "name":            journal.name,
        "issn":            journal.issn or "-",
        "publications":    journal.pub_count or 0,
        "total_citations": journal.total_cit or 0,
        "impact_factor":   journal.impact_factor or "-",
    }


def journal_detail(name_query):
    from journal.models import Journal

    journal = Journal.objects.filter(
        name__icontains=name_query
    ).annotate(
        pub_count=Count('publications'),
        total_cit=Sum('publications__citation_count')
    ).first()

    if not journal:
        return None

    return {
        "name":            journal.name,
        "issn":            journal.issn or "-",
        "impact_factor":   journal.impact_factor or "-",
        "publications":    journal.pub_count or 0,
        "total_citations": journal.total_cit or 0,
    }


# ─── KEYWORDS ─────────────────────────────────────────────────────────────────

def top_keywords(limit=10):
    """Pluriel → liste des N mots-clés les plus fréquents."""
    from keywords.models import Keyword

    keywords = Keyword.objects.annotate(
        pub_count=Count('publications')
    ).order_by('-pub_count')[:limit]

    return [
        {"keyword": kw.label, "publications": kw.pub_count or 0}
        for kw in keywords
    ]


def best_keyword():
    """Singulier → LE mot-clé le plus fréquent."""
    from keywords.models import Keyword

    kw = Keyword.objects.annotate(
        pub_count=Count('publications')
    ).order_by('-pub_count').first()

    if not kw:
        return None

    return {"keyword": kw.label, "publications": kw.pub_count or 0}


def publications_by_keyword(keyword_query, limit=10):
    from publication.models import Publication

    pubs = Publication.objects.filter(
        keywords__label__icontains=keyword_query
    ).order_by('-citation_count')[:limit]

    return [
        {
            "title":     p.title,
            "year":      p.publication_year,
            "citations": p.citation_count,
        }
        for p in pubs
    ]


# ─── STATISTIQUES GÉNÉRALES ───────────────────────────────────────────────────

def general_stats():
    from publication.models import Publication
    from users.models import Researcher
    from journal.models import Journal
    from citation.models import Citation

    total_citations = Publication.objects.aggregate(
        total=Sum('citation_count')
    )['total'] or 0

    top_pub = Publication.objects.order_by('-citation_count').first()

    top_researcher = Researcher.objects.filter(
        user__is_active=True
    ).exclude(
        user__email__icontains="external.openalex"
    ).order_by('-h_index').first()

    return {
        "total_publications":   Publication.objects.count(),
        "total_researchers":    Researcher.objects.filter(
            user__is_active=True
        ).exclude(user__email__icontains="external.openalex").count(),
        "total_journals":       Journal.objects.count(),
        "total_citations":      total_citations,
        "total_citation_links": Citation.objects.count(),
        "most_cited_publication": top_pub.title if top_pub else "-",
        "most_cited_count":     top_pub.citation_count if top_pub else 0,
        "top_researcher":       top_researcher.user.get_full_name() if top_researcher else "-",
        "top_h_index":          top_researcher.h_index if top_researcher else 0,
    }


# ─── CO-AUTEURS ───────────────────────────────────────────────────────────────

def coauthors_of_researcher(name_query):
    from users.models import Researcher
    from coAuthor.models import CoAuthor

    researcher = Researcher.objects.filter(
        Q(user__first_name__icontains=name_query) |
        Q(user__last_name__icontains=name_query)
    ).select_related('user').first()

    if not researcher:
        return None

    pub_ids = CoAuthor.objects.filter(
        author=researcher.user
    ).values_list('publication_id', flat=True)

    coauthors = CoAuthor.objects.filter(
        publication_id__in=pub_ids
    ).exclude(
        author=researcher.user
    ).select_related('author').values(
        'author__first_name', 'author__last_name'
    ).annotate(collab_count=Count('publication_id')).order_by('-collab_count')

    return {
        "researcher": researcher.user.get_full_name(),
        "coauthors": [
            {
                "name":           f"{c['author__first_name']} {c['author__last_name']}".strip(),
                "collaborations": c['collab_count'],
            }
            for c in coauthors
        ]
    }