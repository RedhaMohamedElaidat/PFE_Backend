# data_pipeline/link_researcher_publications.py
# VERSION CORRIGÉE - Gestion des valeurs None

from django.db import transaction
from django.db.models import Q
import requests
import time
import logging
import unicodedata
from datetime import datetime
from collections import Counter

logger = logging.getLogger(__name__)

# Configuration OpenAlex
OPENALEX_BASE_URL = "https://api.openalex.org"
HEADERS = {"User-Agent": "mailto:ridaelaidate7@gmail.com"}


def normalize_name(name: str) -> str:
    """Normalise un nom pour la recherche"""
    if not name:
        return ""
    name = name.lower()
    name = ''.join(
        c for c in unicodedata.normalize('NFD', name)
        if unicodedata.category(c) != 'Mn'
    )
    name = name.replace('.', '').replace(',', ' ').replace('-', ' ')
    name = ' '.join(name.split())
    return name.strip()


def fetch_openalex_works_by_orcid(orcid: str, start_year: int = 2010, end_year: int = 2026) -> list:
    """
    Récupère toutes les publications d'un auteur depuis OpenAlex par son ORCID
    """
    print(f"\n  🔍 Fetch OpenAlex pour ORCID: {orcid} ({start_year}-{end_year})")
    
    all_works = []
    cursor = "*"
    page = 0
    
    # Nettoyer l'ORCID
    clean_orcid = orcid.replace("https://orcid.org/", "").strip()
    
    while cursor:
        page += 1
        try:
            params = {
                "filter": f"author.orcid:{clean_orcid},publication_year:{start_year}-{end_year}",
                "per_page": 200,
                "cursor": cursor,
                "sort": "publication_year:desc",
            }
            
            response = requests.get(
                f"{OPENALEX_BASE_URL}/works",
                params=params,
                headers=HEADERS,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            meta = data.get("meta", {})
            
            if not results:
                break
            
            all_works.extend(results)
            cursor = meta.get("next_cursor")
            
            print(f"     Page {page}: {len(results)} publications (Total: {len(all_works)})")
            
            time.sleep(0.3)
            
        except Exception as e:
            logger.error(f"Erreur fetch OpenAlex par ORCID: {e}")
            break
    
    print(f"     ✅ Total trouvé: {len(all_works)} publications")
    
    for work in all_works:
        title = work.get("title", "Sans titre")[:60]
        year = work.get("publication_year", "?")
        print(f"        - {title}... ({year})")
    
    return all_works


def reconstruct_abstract(inverted_index: dict) -> str:
    """Reconstruit l'abstract depuis l'inverted index"""
    if not inverted_index:
        return ""
    try:
        positions = []
        for word, pos_list in inverted_index.items():
            for pos in pos_list:
                positions.append((pos, word))
        positions.sort(key=lambda x: x[0])
        return " ".join(w for _, w in positions)
    except Exception:
        return ""


def map_contribution_type(order: int, authorship: dict) -> int:
    """Map la contribution type"""
    if authorship.get("is_corresponding", False):
        return 4
    if order == 1:
        return 1
    if order == 2:
        return 2
    if order == 3:
        return 3
    return 5


def import_missing_publications(works: list, user) -> dict:
    """
    Importe les publications manquantes dans la base de données
    """
    from publication.models import Publication
    from journal.models import Journal
    from keywords.models import Keyword
    from coAuthor.models import CoAuthor
    from users.models import Researcher
    
    print(f"\n  📥 Import des publications manquantes...")
    
    stats = {
        "new_publications": 0,
        "new_coauthors": 0,
        "new_journals": 0,
        "new_keywords": 0,
        "errors": 0
    }
    
    # Filtrer les publications qui n'existent pas déjà
    existing_openalex_ids = set(
        Publication.objects.filter(
            openalex_id__in=[w.get("id") for w in works if w.get("id")]
        ).values_list('openalex_id', flat=True)
    )
    
    new_works = [w for w in works if w.get("id") not in existing_openalex_ids]
    
    if not new_works:
        print(f"     ℹ️  Aucune nouvelle publication à importer")
        return stats
    
    print(f"     📊 {len(new_works)} nouvelles publications à importer")
    
    with transaction.atomic():
        
        # 1. Importer les journaux
        journals_cache = {}
        for work in new_works:
            source = (work.get("primary_location") or {}).get("source") or {}
            name = source.get("display_name", "").strip()
            if name:
                issns = source.get("issn", [])
                issn = issns[0] if issns else None
                
                journal, created = Journal.objects.get_or_create(
                    issn=issn if issn else name,
                    defaults={'name': name, 'issn': issn}
                )
                if created:
                    stats["new_journals"] += 1
                journals_cache[work.get("id")] = journal
        
        # 2. Importer les keywords
        keywords_cache = {}
        all_keywords = set()
        for work in new_works:
            for concept in (work.get("concepts") or [])[:8]:
                label = concept.get("display_name", "").strip().lower()
                if label:
                    all_keywords.add(label)
        
        for label in all_keywords:
            keyword, created = Keyword.objects.get_or_create(label=label)
            if created:
                stats["new_keywords"] += 1
            keywords_cache[label] = keyword
        
        # 3. Créer les publications
        researcher, _ = Researcher.objects.get_or_create(user=user)
        
        for work in new_works:
            try:
                title = work.get("title", "").strip()
                if not title:
                    continue
                
                oid = work.get("id")
                
                # CORRECTION: Gérer le cas où doi est None
                doi_raw = work.get("doi")
                if doi_raw and isinstance(doi_raw, str):
                    doi = doi_raw.replace("https://doi.org/", "").strip()
                else:
                    doi = None
                
                # CORRECTION: Gérer l'abstract
                abstract_raw = work.get("abstract_inverted_index")
                if abstract_raw:
                    abstract = reconstruct_abstract(abstract_raw)
                else:
                    abstract = ""
                
                pub_year = work.get("publication_year")
                citation_count = work.get("cited_by_count", 0)
                journal = journals_cache.get(oid)
                
                # Déterminer le type de publication
                pub_type = work.get("type", "journal-article")
                if pub_type == "journal-article":
                    pub_type_display = "Article"
                elif pub_type == "book":
                    pub_type_display = "Book"
                elif pub_type == "proceedings-article":
                    pub_type_display = "Conference_Paper"
                elif pub_type == "review-article":
                    pub_type_display = "Review"
                else:
                    pub_type_display = "Article"
                
                pub, created = Publication.objects.get_or_create(
                    openalex_id=oid,
                    defaults={
                        'title': title[:1000],
                        'abstract': abstract,
                        'publication_year': pub_year,
                        'doi': doi,
                        'type': pub_type_display,
                        'citation_count': citation_count,
                        'journal': journal,
                        'is_validated': True,
                    }
                )
                
                if created:
                    stats["new_publications"] += 1
                    
                    # Ajouter les keywords
                    for concept in (work.get("concepts") or [])[:8]:
                        label = concept.get("display_name", "").strip().lower()
                        keyword = keywords_cache.get(label)
                        if keyword:
                            pub.keywords.add(keyword)
                    
                    # Lier au chercheur
                    pub.reseachers.add(researcher)
                    
                    # Créer les co-authors
                    authorships = work.get("authorships", [])
                    for order, authorship in enumerate(authorships, start=1):
                        author = authorship.get("author", {})
                        author_name = author.get("display_name", "").strip()
                        
                        if not author_name:
                            continue
                        
                        author_orcid = author.get("orcid", "")
                        if author_orcid:
                            author_orcid = author_orcid.replace("https://orcid.org/", "")
                        
                        openalex_id = author.get("id")
                        
                        institutions = authorship.get("institutions", [])
                        affiliation = institutions[0].get("display_name", "") if institutions else ""
                        
                        contribution_type = map_contribution_type(order, authorship)
                        
                        # Vérifier si c'est l'utilisateur lui-même
                        is_self = (normalize_name(author_name) == normalize_name(user.get_full_name()))
                        
                        coauthor, created = CoAuthor.objects.get_or_create(
                            publication=pub,
                            author_name=author_name,
                            author_order=order,
                            defaults={
                                'author_orcid': author_orcid or None,
                                'openalex_id': openalex_id,
                                'contribution_type': contribution_type,
                                'affiliation_at_time': affiliation[:255] if affiliation else "",
                                'linked_user': user if is_self else None
                            }
                        )
                        if created:
                            stats["new_coauthors"] += 1
                            
            except Exception as e:
                logger.error(f"Erreur import publication: {e}")
                stats["errors"] += 1
    
    print(f"     ✅ Import terminé: {stats['new_publications']} nouvelles publications")
    return stats


def check_and_sync_missing_publications(
    user, 
    start_year: int = 2010, 
    end_year: int = 2026
) -> dict:
    """
    Vérifie et synchronise les publications manquantes d'un chercheur
    """
    from users.models import Researcher
    
    print(f"\n{'='*70}")
    print(f"  🔄 CHECK & SYNC MISSING PUBLICATIONS")
    print(f"  User: {user.username}")
    print(f"  Nom: {user.get_full_name()}")
    print(f"  Période: {start_year} - {end_year}")
    print(f"{'='*70}\n")
    
    stats = {
        "openalex_count": 0,
        "local_count": 0,
        "missing_count": 0,
        "imported_count": 0,
        "errors": 0
    }
    
    try:
        researcher, created = Researcher.objects.get_or_create(user=user)
        
        # Récupérer les publications locales
        local_publications = researcher.publications.filter(
            publication_year__gte=start_year,
            publication_year__lte=end_year
        )
        stats["local_count"] = local_publications.count()
        print(f"  📊 Base locale: {stats['local_count']} publications")
        
        # Récupérer depuis OpenAlex par ORCID
        openalex_works = []
        
        if researcher.orcid:
            openalex_works = fetch_openalex_works_by_orcid(researcher.orcid, start_year, end_year)
        
        stats["openalex_count"] = len(openalex_works)
        print(f"  📊 OpenAlex: {stats['openalex_count']} publications trouvées")
        
        stats["missing_count"] = stats["openalex_count"] - stats["local_count"]
        
        if stats["missing_count"] == 0:
            print(f"\n  ✅ Toutes les publications sont synchronisées!")
            print(f"     {stats['local_count']}/{stats['openalex_count']} publications")
        elif stats["missing_count"] > 0:
            print(f"\n  ⚠️  {stats['missing_count']} publications manquantes détectées")
            print(f"  🔄 Synchronisation en cours...")
            
            import_stats = import_missing_publications(openalex_works, user)
            stats["imported_count"] = import_stats["new_publications"]
            stats["errors"] = import_stats["errors"]
            
            print(f"\n  ✅ Synchronisation terminée:")
            print(f"     Nouvelles publications: {import_stats['new_publications']}")
            print(f"     Nouveaux co-authors: {import_stats['new_coauthors']}")
            print(f"     Nouveaux journaux: {import_stats['new_journals']}")
            print(f"     Nouveaux keywords: {import_stats['new_keywords']}")
            
            # Mettre à jour le H-Index
            update_h_index(researcher)
        
        final_count = researcher.publications.filter(
            publication_year__gte=start_year,
            publication_year__lte=end_year
        ).count()
        
        print(f"\n{'='*70}")
        print(f"  📊 RÉSUMÉ FINAL")
        print(f"  Publications OpenAlex: {stats['openalex_count']}")
        print(f"  Publications en base: {final_count}")
        print(f"  Publications importées: {stats['imported_count']}")
        print(f"{'='*70}\n")
        
    except Exception as e:
        logger.error(f"Erreur dans check_and_sync_missing_publications: {e}")
        import traceback
        traceback.print_exc()
        stats["errors"] += 1
        print(f"\n  ❌ Erreur: {e}")
    
    return stats


def update_h_index(researcher):
    """Met à jour le H-Index du chercheur"""
    
    publications = researcher.publications.all()
    
    if not publications:
        if researcher.h_index != 0:
            researcher.h_index = 0
            researcher.save(update_fields=['h_index'])
        return 0
    
    # ✅ CORRECTION : Utiliser citation_count directement depuis la publication
    citation_counts = []
    for pub in publications:
        # Utiliser le champ citation_count de la publication
        citations = pub.citation_count or 0
        citation_counts.append(citations)
        print(f"     Publication: {pub.title[:50]}... ({citations} citations)")
    
    if citation_counts:
        citation_counts.sort(reverse=True)
        h_index = 0
        for i, citations in enumerate(citation_counts, 1):
            if citations >= i:
                h_index = i
            else:
                break
        
        if researcher.h_index != h_index:
            researcher.h_index = h_index
            researcher.save(update_fields=['h_index'])
            print(f"  📊 H-Index mis à jour: {h_index}")
            return h_index
        else:
            print(f"  📊 H-Index inchangé: {h_index}")
    
    return 0


def find_coauthors_by_name(user, author_name=None):
    """Cherche les CoAuthors par le nom de l'utilisateur"""
    from coAuthor.models import CoAuthor
    
    coauthors = []
    seen_ids = set()
    
    search_name = author_name or user.get_full_name()
    first_name = user.first_name
    last_name = user.last_name
    
    print(f"\n  🔍 Recherche par nom: '{search_name}'")
    
    # Stratégie 1: Nom exact (insensible à la casse)
    results = CoAuthor.objects.filter(
        author_name__iexact=search_name
    ).select_related('publication')
    
    for ca in results:
        if ca.ID not in seen_ids:
            coauthors.append(ca)
            seen_ids.add(ca.ID)
            print(f"     ✅ Trouvé (exact): '{ca.author_name}'")
    
    # Stratégie 2: Contient le prénom ET le nom
    if first_name and last_name:
        results = CoAuthor.objects.filter(
            Q(author_name__icontains=first_name) & 
            Q(author_name__icontains=last_name)
        ).select_related('publication')
        
        for ca in results:
            if ca.ID not in seen_ids:
                coauthors.append(ca)
                seen_ids.add(ca.ID)
                print(f"     ✅ Trouvé (prénom+nom): '{ca.author_name}'")
    
    return coauthors


def link_by_name(user, author_name=None, auto_sync_missing=True):
    """Lie les publications d'un chercheur par son NOM"""
    from users.models import Researcher
    from collections import Counter
    
    print(f"\n{'='*70}")
    print(f"  🔗 LINKING RESEARCHER BY NAME")
    print(f"  User: {user.username}")
    print(f"  Email: {user.email}")
    print(f"  Nom complet: {user.get_full_name()}")
    print(f"{'='*70}\n")
    
    stats = {
        "coauthors_found": 0,
        "coauthors_updated": 0,
        "publications_linked": 0,
        "publications_already_linked": 0,
        "publications_total": 0,
        "missing_sync": None,
        "errors": 0
    }
    
    try:
        with transaction.atomic():
            
            if auto_sync_missing:
                print(f"  🔄 Vérification des publications manquantes...")
                sync_stats = check_and_sync_missing_publications(user, 2010, 2026)
                stats["missing_sync"] = sync_stats
            
            coauthors = find_coauthors_by_name(user, author_name)
            
            if not coauthors:
                print(f"\n  ⚠️  Aucune publication trouvée pour '{user.get_full_name()}'")
                return stats
            
            stats["coauthors_found"] = len(coauthors)
            
            unique_pubs = {}
            for ca in coauthors:
                if ca.publication.id not in unique_pubs:
                    unique_pubs[ca.publication.id] = ca.publication
                    pub = ca.publication
                    title = pub.title[:60] if pub.title else "Sans titre"
                    year = pub.publication_year or "?"
                    print(f"  📄 '{title}...' ({year})")
            
            print(f"\n  📊 Total trouvé: {len(coauthors)} co-auteurs, {len(unique_pubs)} publications")
            
            for ca in coauthors:
                if ca.linked_user is None:
                    ca.linked_user = user
                    ca.save()
                    stats["coauthors_updated"] += 1
            
            if stats["coauthors_updated"] > 0:
                print(f"  ✅ {stats['coauthors_updated']} CoAuthors mis à jour")
            
            researcher, created = Researcher.objects.get_or_create(user=user)
            if created:
                print(f"  🆕 Nouveau chercheur créé")
            
            stats["publications_total"] = len(unique_pubs)
            
            publications_to_link = []
            for pub in unique_pubs.values():
                if not pub.reseachers.filter(id=researcher.id).exists():
                    publications_to_link.append(pub)
                    stats["publications_linked"] += 1
                else:
                    stats["publications_already_linked"] += 1
            
            if publications_to_link:
                researcher.publications.add(*publications_to_link)
                print(f"  ✅ {stats['publications_linked']} publications liées")
            
            if stats["publications_already_linked"] > 0:
                print(f"  ℹ️  {stats['publications_already_linked']} déjà liées")
            
            update_h_index(researcher)
            
            
    
    except Exception as e:
        logger.error(f"Erreur dans link_by_name: {e}")
        import traceback
        traceback.print_exc()
        stats["errors"] += 1
        print(f"\n  ❌ Erreur: {e}")
    
    print(f"\n  ✅ LINKING COMPLÉTÉ")
    print(f"     CoAuthors liés: {stats['coauthors_updated']}")
    print(f"     Publications liées: {stats['publications_linked']}/{stats['publications_total']}")
    print(f"{'='*70}\n")
    
    return stats


def link_by_orcid(user, orcid, auto_sync_missing=True):
    """Lie les publications d'un chercheur par son ORCID"""
    from users.models import Researcher
    from coAuthor.models import CoAuthor
    
    print(f"\n{'='*70}")
    print(f"  🔗 LINKING RESEARCHER BY ORCID")
    print(f"  User: {user.username}")
    print(f"  ORCID: {orcid}")
    print(f"{'='*70}\n")
    
    stats = {
        "coauthors_found": 0,
        "coauthors_updated": 0,
        "publications_linked": 0,
        "publications_total": 0,
        "missing_sync": None,
        "errors": 0
    }
    
    try:
        with transaction.atomic():
            
            if auto_sync_missing:
                print(f"  🔄 Vérification des publications manquantes...")
                sync_stats = check_and_sync_missing_publications(user, 2010, 2026)
                stats["missing_sync"] = sync_stats
            
            coauthors = CoAuthor.objects.filter(
                author_orcid=orcid
            ).select_related('publication')
            
            stats["coauthors_found"] = coauthors.count()
            print(f"  📚 CoAuthors trouvés: {stats['coauthors_found']}")
            
            if stats["coauthors_found"] == 0:
                print(f"  ⚠️  Aucune publication trouvée pour cet ORCID")
                return stats
            
            unique_pubs = {}
            for ca in coauthors:
                if ca.publication.id not in unique_pubs:
                    unique_pubs[ca.publication.id] = ca.publication
                    pub = ca.publication
                    title = pub.title[:60] if pub.title else "Sans titre"
                    year = pub.publication_year or "?"
                    print(f"  📄 '{title}...' ({year})")
            
            for ca in coauthors:
                if ca.linked_user is None:
                    ca.linked_user = user
                    ca.save()
                    stats["coauthors_updated"] += 1
            
            researcher, created = Researcher.objects.get_or_create(user=user)
            stats["publications_total"] = len(unique_pubs)
            
            publications_to_link = []
            for pub in unique_pubs.values():
                if not pub.reseachers.filter(id=researcher.id).exists():
                    publications_to_link.append(pub)
                    stats["publications_linked"] += 1
            
            if publications_to_link:
                researcher.publications.add(*publications_to_link)
                print(f"  ✅ {stats['publications_linked']} publications liées")
            
            update_h_index(researcher)
            
    except Exception as e:
        logger.error(f"Erreur dans link_by_orcid: {e}")
        stats["errors"] += 1
    
    print(f"\n  ✅ LINKING COMPLÉTÉ")
    return stats


# Pour la compatibilité avec l'ancien code
def link_researcher_publications(user, orcid=None, author_name=None):
    """Wrapper pour la compatibilité"""
    if orcid:
        return link_by_orcid(user, orcid, auto_sync_missing=True)
    else:
        return link_by_name(user, author_name, auto_sync_missing=True)