"""
fetch_algeria_openalex.py - VERSION COMPLÈTE OPTIMISÉE
Mode GLOBAL : Récupère TOUTES les publications Algérie (2010-2025)
Indépendant du mode INDIVIDUEL (openalex_researcher_sync.py)

Flux :
OpenAlex API (filter: country_code:DZ) 
    ↓
Extraction & normalisation
    ↓
PostgreSQL (stockage brut complet)
    ↓
Prêt pour Bibliometrix
"""

import requests
import time
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from django.db import transaction
from django.db import models

logger = logging.getLogger(__name__)
BASE_URL = "https://api.openalex.org"
HEADERS = {"User-Agent": "mailto:ridaelaidate7@gmail.com"}

# Configuration des retries pour les requêtes
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504]
)
session.mount('https://', HTTPAdapter(max_retries=retries))
session.mount('http://', HTTPAdapter(max_retries=retries))


# ─────────────────────────────────────────────────────────────────────────────
# 📊 METRICS FUNCTIONS (intégrées directement)
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
        
        # Altmetric Score = citations(60%) + keywords(20%) + coauthors(20%)
        score = citations * 0.6 + keywords * 0.2 + coauthors * 0.2
        pub.altmetric_score = round(score, 2)
        to_update.append(pub)
    
    if to_update:
        Publication.objects.bulk_update(to_update, ["altmetric_score"])
        print(f"  📊 Altmetric: {len(to_update)} pubs mis à jour")


def fetch_journal_impact_factors_batch(journals_map: dict = None, batch_size: int = 50) -> int:
    """
    Récupère les Impact Factors en BATCH (beaucoup plus rapide !)
    Utilise le filter OR d'OpenAlex pour traiter plusieurs journaux par requête
    """
    from journal.models import Journal
    
    # Récupérer les journaux uniques (sans doublons)
    if journals_map:
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
            response = session.get(
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


# ─────────────────────────────────────────────────────────────────────────────
# 🟢 ÉTAPE 1 : FETCH depuis OpenAlex
# ─────────────────────────────────────────────────────────────────────────────

def fetch_algeria_publications(
    start_year: int = 2010,
    end_year: int = 2025,
    batch_size: int = 200
) -> List[Dict]:
    """
    Récupère TOUTES les publications Algérie via OpenAlex
    
    Paramètres :
    - country_code:DZ = Algérie uniquement
    - publication_year:2010-2025 = Période
    - per_page=200 = Max par requête
    - cursor=* = Pagination correcte
    
    Retourne : Liste complète des works OpenAlex
    """
    
    print(f"\n{'='*70}")
    print(f"  🇩🇿 FETCH PUBLICATIONS ALGÉRIE ({start_year}-{end_year})")
    print(f"{'='*70}\n")
    
    all_works = []
    cursor = "*"
    page = 0
    start_time = time.time()
    
    while cursor:
        page += 1
        print(f"  📄 Page {page} (cursor: {cursor[:20]}...)")
        
        try:
            params = {
                "filter": f"authorships.institutions.country_code:DZ,publication_year:{start_year}-{end_year}",
                "per_page": batch_size,
                "cursor": cursor,
                "sort": "publication_year:desc",
                "select": ",".join([
                    "id",
                    "title",
                    "abstract_inverted_index",
                    "publication_year",
                    "doi",
                    "type",
                    "cited_by_count",
                    "authorships",
                    "primary_location",
                    "concepts",
                    "referenced_works",
                ]),
            }
            
            response = session.get(
                f"{BASE_URL}/works",
                params=params,
                headers=HEADERS,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            meta = data.get("meta", {})
            
            if not results:
                print(f"     ❌ Aucun résultat à cette page")
                break
            
            all_works.extend(results)
            cursor = meta.get("next_cursor")
            
            print(f"     ✅ {len(results)} publications (Total: {len(all_works)})")
            print(f"     ⏱️  Temps écoulé: {round(time.time() - start_time, 1)}s")
            
            # Rate limiting
            time.sleep(0.5)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur fetch page {page}: {e}")
            print(f"     ❌ Erreur: {e}")
            if hasattr(response, 'status_code') and response.status_code == 429:
                print(f"     ⏳ Rate limit - attendre 30s...")
                time.sleep(30)
            else:
                break
        except Exception as e:
            logger.error(f"Erreur inattendue page {page}: {e}")
            print(f"     ❌ Erreur inattendue: {e}")
            break
    
    elapsed = round(time.time() - start_time, 1)
    print(f"\n  ✅ FETCH COMPLÈTE")
    print(f"     📊 Total publications: {len(all_works)}")
    print(f"     ⏱️  Temps total: {elapsed}s")
    print(f"     📈 Moyenne: {round(len(all_works) / (elapsed/60) if elapsed > 0 else 0, 0)}/min\n")
    
    return all_works


# ─────────────────────────────────────────────────────────────────────────────
# 🟡 ÉTAPE 2 : TRANSFORMATION & STOCKAGE
# ─────────────────────────────────────────────────────────────────────────────

def process_and_store_publications(works: List[Dict]) -> Dict:
    """
    Traite les works OpenAlex et les stocke en PostgreSQL
    
    Crée/met à jour :
    - Publication
    - Journal
    - Keyword
    - CoAuthor (liens externes, PAS d'auto-création User)
    - Citation (références internes)
    
    Retourne : Statistiques
    """
    
    print(f"\n{'='*70}")
    print(f"  🟡 STOCKAGE EN POSTGRESQL")
    print(f"{'='*70}\n")
    
    if not works:
        print("  ❌ Aucune publication à traiter")
        return {"created": 0, "updated": 0, "errors": 0}
    
    start_time = time.time()
    stats = {
        "publications_created": 0,
        "publications_updated": 0,
        "publications_errors": 0,
        "journals_created": 0,
        "keywords_created": 0,
        "coauthors_created": 0,
        "citations_created": 0,
    }
    
    with transaction.atomic():
        
        # ────────────────── ÉTAPE 2.1 : Journaux ──────────────────
        t = time.time()
        journals_map = _bulk_get_or_create_journals(works)
        stats["journals_created"] = len(journals_map)
        print(f"  📰 Journaux: {stats['journals_created']} ({round(time.time()-t, 1)}s)")
        
        # ────────────────── ÉTAPE 2.2 : Keywords ──────────────────
        t = time.time()
        keywords_map = _bulk_get_or_create_keywords(works)
        stats["keywords_created"] = len(keywords_map)
        print(f"  🏷️  Keywords: {stats['keywords_created']} ({round(time.time()-t, 1)}s)")
        
        # ────────────────── ÉTAPE 2.3 : Publications ──────────────
        t = time.time()
        publications_map, pub_stats = _bulk_get_or_create_publications(works, journals_map)
        stats["publications_created"] = pub_stats["created"]
        stats["publications_updated"] = pub_stats["updated"]
        stats["publications_errors"] = pub_stats["errors"]
        print(f"  📄 Publications: {pub_stats['created']} créées, "
              f"{pub_stats['updated']} MAJ ({round(time.time()-t, 1)}s)")
        
        # ────────────────── ÉTAPE 2.4 : Keywords M2M ──────────────
        t = time.time()
        _bulk_assign_keywords(works, publications_map, keywords_map)
        print(f"  🔗 Keywords assignés ({round(time.time()-t, 1)}s)")
        
        # ────────────────── ÉTAPE 2.5 : CoAuthors ─────────────────
        t = time.time()
        nb_coauthors = _bulk_process_coauthors(works, publications_map)
        stats["coauthors_created"] = nb_coauthors
        print(f"  👥 CoAuthors: {nb_coauthors} ({round(time.time()-t, 1)}s)")
        
        # ────────────────── ÉTAPE 2.6 : Citations ─────────────────
        t = time.time()
        nb_citations = _bulk_process_citations(works, publications_map)
        stats["citations_created"] = nb_citations
        print(f"  🔗 Citations: {nb_citations} ({round(time.time()-t, 1)}s)")

        # ────────────────── ÉTAPE 2.7 : Altmetric Score ────────────────
        t = time.time()
        compute_altmetric_scores(publications_map)
        print(f"  📊 Altmetric Score ({round(time.time()-t, 1)}s)")

        # ────────────────── ÉTAPE 2.8 : Impact Factors (BATCH) ─────────
        t = time.time()
        nb_journals = fetch_journal_impact_factors_batch(journals_map, batch_size=50)
        print(f"  📰 Impact Factors: {nb_journals} journaux ({round(time.time()-t, 1)}s)")
    
    elapsed = round(time.time() - start_time, 1)
        
    print(f"\n  ✅ STOCKAGE COMPLÈTE ({elapsed}s)")
    print(f"     📊 Publications: {stats['publications_created']} créées, {stats['publications_updated']} MAJ")
    print(f"     📊 CoAuthors: {stats['coauthors_created']}")
    print(f"     📊 Citations: {stats['citations_created']}\n")
    
    return stats


def _bulk_get_or_create_journals(works: List[Dict]) -> Dict:
    """Crée/récupère les journaux - VERSION SANS DOUBLONS"""
    from journal.models import Journal
    
    # Utiliser l'ISSN comme clé unique
    journals_by_issn = {}
    journals_by_name = {}
    
    for work in works:
        source = (work.get("primary_location") or {}).get("source") or {}
        name = (source.get("display_name") or "").strip()[:500]
        if not name:
            continue
        
        issns = source.get("issn") or []
        issn = issns[0] if issns else None
        
        if issn:
            # Priorité à l'ISSN
            if issn not in journals_by_issn:
                journals_by_issn[issn] = {"name": name, "issn": issn}
        else:
            # Sans ISSN, utiliser le nom
            if name not in journals_by_name:
                journals_by_name[name] = {"name": name, "issn": None}
    
    # Récupérer les existants par ISSN
    existing_issn = {}
    if journals_by_issn:
        issn_list = list(journals_by_issn.keys())
        for journal in Journal.objects.filter(issn__in=issn_list):
            existing_issn[journal.issn] = journal
    
    # Récupérer les existants par nom (sans ISSN)
    existing_name = {}
    if journals_by_name:
        name_list = list(journals_by_name.keys())
        for journal in Journal.objects.filter(name__in=name_list, issn__isnull=True):
            existing_name[journal.name] = journal
    
    # Créer les nouveaux journaux
    to_create = []
    
    # Journaux avec ISSN
    for issn, data in journals_by_issn.items():
        if issn not in existing_issn:
            to_create.append(Journal(name=data["name"], issn=issn))
    
    # Journaux sans ISSN
    for name, data in journals_by_name.items():
        if name not in existing_name:
            to_create.append(Journal(name=data["name"], issn=None))
    
    if to_create:
        Journal.objects.bulk_create(to_create, ignore_conflicts=True)
        
        # Recharger les nouveaux
        for journal in Journal.objects.filter(
            name__in=[j.name for j in to_create]
        ):
            if journal.issn:
                existing_issn[journal.issn] = journal
            else:
                existing_name[journal.name] = journal
    
    # Mapping final work_id -> Journal
    result = {}
    for work in works:
        source = (work.get("primary_location") or {}).get("source") or {}
        name = (source.get("display_name") or "").strip()[:500]
        if not name:
            continue
        
        issns = source.get("issn") or []
        issn = issns[0] if issns else None
        work_id = work.get("id", "")
        
        if work_id:
            if issn and issn in existing_issn:
                result[work_id] = existing_issn[issn]
            elif not issn and name in existing_name:
                result[work_id] = existing_name[name]
    
    return result


def _bulk_get_or_create_keywords(works: List[Dict]) -> Dict:
    """Crée/récupère les keywords depuis les concepts"""
    from keywords.models import Keyword
    
    all_labels = set()
    for work in works:
        for c in (work.get("concepts") or [])[:8]:
            label = (c.get("display_name") or "").strip().lower()
            if label:
                all_labels.add(label)
    
    if not all_labels:
        return {}
    
    existing = {kw.label: kw for kw in Keyword.objects.filter(label__in=all_labels)}
    
    to_create = [Keyword(label=l) for l in all_labels if l not in existing]
    if to_create:
        Keyword.objects.bulk_create(to_create, ignore_conflicts=True)
        for kw in Keyword.objects.filter(label__in=all_labels):
            existing[kw.label] = kw
    
    return existing


def _bulk_get_or_create_publications(works: List[Dict], journals_map: Dict) -> Tuple[Dict, Dict]:
    """Crée/met à jour les publications"""
    from publication.models import Publication, PublicationType
    from institution.models import Institution
    
    type_map = {
        "journal-article": PublicationType.ARTICLE,
        "book": PublicationType.BOOK,
        "proceedings-article": PublicationType.CONFERENCE_PAPER,
        "review-article": PublicationType.REVIEW,
        "book-chapter": PublicationType.BOOK,
    }
    
    openalex_ids = [w.get("id") for w in works if w.get("id")]
    dois = [
        w.get("doi", "").replace("https://doi.org/", "").strip()
        for w in works if w.get("doi")
    ]
    
    existing_by_openalex = {
        p.openalex_id: p
        for p in Publication.objects.filter(openalex_id__in=openalex_ids)
    }
    existing_by_doi = {
        p.doi: p
        for p in Publication.objects.filter(doi__in=dois) if p.doi
    }
    
    publications_map = {}
    to_create = []
    to_update = []
    stats = {"created": 0, "updated": 0, "errors": 0}
    
    for work in works:
        try:
            title = (work.get("title") or "").strip()
            if not title:
                continue
            
            oid = work.get("id", "") or None
            doi = (work.get("doi") or "").replace("https://doi.org/", "").strip() or None
            abstract = _reconstruct_abstract(work.get("abstract_inverted_index") or {})
            pub_type = type_map.get(work.get("type", ""), PublicationType.ARTICLE)
            journal = journals_map.get(oid)
            
            # Récupérer l'institution principale
            inst = _get_first_institution(work)
            
            pub = existing_by_openalex.get(oid)
            if not pub and doi:
                pub = existing_by_doi.get(doi)
            
            if pub:
                pub.citation_count = work.get("cited_by_count", 0)
                if inst and not pub.institution:
                    pub.institution = inst
                if oid and not pub.openalex_id:
                    pub.openalex_id = oid
                to_update.append(pub)
                if oid:
                    publications_map[oid] = pub
                stats["updated"] += 1
            else:
                new_pub = Publication(
                    title=title[:1000],
                    abstract=abstract,
                    publication_year=work.get("publication_year"),
                    doi=doi,
                    openalex_id=oid,
                    type=pub_type,
                    journal=journal,
                    institution=inst,
                    citation_count=work.get("cited_by_count", 0),
                    is_validated=True,
                )
                to_create.append((oid, new_pub))
        
        except Exception as e:
            logger.error(f"Erreur publication: {e}")
            stats["errors"] += 1
    
    if to_create:
        Publication.objects.bulk_create(
            [p for _, p in to_create], ignore_conflicts=True
        )
        stats["created"] = len(to_create)
        created_oids = [oid for oid, _ in to_create if oid]
        for pub in Publication.objects.filter(openalex_id__in=created_oids):
            publications_map[pub.openalex_id] = pub
    
    if to_update:
        Publication.objects.bulk_update(
            to_update, ["citation_count", "institution", "openalex_id"]
        )
    
    return publications_map, stats


def _bulk_assign_keywords(works: List[Dict], publications_map: Dict, keywords_map: Dict):
    """Assigne les keywords aux publications (M2M)"""
    from publication.models import Publication
    PublicationKeyword = Publication.keywords.through
    
    pub_ids = [p.id for p in publications_map.values()]
    existing = set(
        PublicationKeyword.objects.filter(
            publication_id__in=pub_ids
        ).values_list('publication_id', 'keyword_id')
    )
    
    to_create = []
    for work in works:
        oid = work.get("id", "")
        pub = publications_map.get(oid)
        if not pub:
            continue
        
        for c in (work.get("concepts") or [])[:8]:
            label = (c.get("display_name") or "").strip().lower()
            kw = keywords_map.get(label)
            if kw and (pub.id, kw.id) not in existing:
                to_create.append(PublicationKeyword(
                    publication_id=pub.id, keyword_id=kw.id
                ))
                existing.add((pub.id, kw.id))
    
    if to_create:
        PublicationKeyword.objects.bulk_create(to_create, ignore_conflicts=True)


def _bulk_process_coauthors(works: List[Dict], publications_map: Dict) -> int:
    """
    Crée les entrées CoAuthor pour TOUS les auteurs.
    
    ⚠️ IMPORTANT : Pas de création User automatique
    - Stocke author_name, author_orcid, openalex_id
    - linked_user = None (sauf si ORCID correspond à un User existant)
    """
    from coAuthor.models import CoAuthor
    from users.models import Researcher
    
    print(f"\n   👥 Début bulk_process_coauthors")
    
    # Charger les users connus via ORCID
    known_users = {
        r.orcid: r.user
        for r in Researcher.objects.select_related('user')
        if r.orcid
    }
    
    pub_ids = [p.id for p in publications_map.values()]
    existing_coauthors = CoAuthor.objects.filter(publication_id__in=pub_ids)
    
    existing_keys = set()
    for ca in existing_coauthors:
        if ca.author_orcid:
            key = (ca.publication_id, ca.author_orcid, ca.author_order)
        else:
            identifier = ca.openalex_id or ca.author_name
            key = (ca.publication_id, identifier, ca.author_order)
        existing_keys.add(key)
    
    coauthors_to_create = []
    
    for work in works:
        oid = work.get("id", "")
        pub = publications_map.get(oid)
        if not pub:
            continue
        
        for order, authorship in enumerate(work.get("authorships") or [], start=1):
            author = authorship.get("author") or {}
            
            name = (author.get("display_name") or "").strip()
            orcid = (author.get("orcid") or "").replace("https://orcid.org/", "").strip() or None
            openalex_id = author.get("id")
            
            if not name:
                continue
            
            inst_list = authorship.get("institutions") or []
            affiliation = inst_list[0].get("display_name", "") if inst_list else ""
            
            # Déterminer linked_user SEULEMENT si ORCID existe et correspond à un User
            linked_user = None
            if orcid and orcid in known_users:
                linked_user = known_users[orcid]
            
            contribution_type = _map_contribution(order, authorship)
            
            # Clé unique
            if orcid:
                key = (pub.id, orcid, order)
            elif openalex_id:
                key = (pub.id, openalex_id, order)
            else:
                key = (pub.id, name, order)
            
            if key not in existing_keys:
                coauthor = CoAuthor(
                    publication=pub,
                    author_name=name[:255],
                    author_orcid=orcid,
                    openalex_id=openalex_id,
                    linked_user=linked_user,
                    contribution_type=contribution_type,
                    author_order=order,
                    affiliation_at_time=(affiliation or "")[:255],
                )
                coauthors_to_create.append(coauthor)
                existing_keys.add(key)
    
    if coauthors_to_create:
        CoAuthor.objects.bulk_create(coauthors_to_create, ignore_conflicts=True)
    
    print(f"      ✅ {len(coauthors_to_create)} CoAuthors créées")
    return len(coauthors_to_create)


def _bulk_process_citations(works: List[Dict], publications_map: Dict) -> int:
    """Crée les citations internes (publication A → publication B)"""
    from citation.models import Citation, DataSource
    
    all_ref_ids = set()
    for work in works:
        for ref_id in (work.get("referenced_works") or []):
            all_ref_ids.add(ref_id)
    
    if not all_ref_ids:
        return 0
    
    pub_ids = [p.id for p in publications_map.values() if p.id]
    if not pub_ids:
        return 0
    
    existing = set(
        Citation.objects.filter(
            citing_publication_id__in=pub_ids
        ).values_list('citing_publication_id', 'cited_publication_id')
    )
    
    to_create = []
    for work in works:
        oid = work.get("id", "")
        citing_pub = publications_map.get(oid)
        if not citing_pub:
            continue
        
        for ref_id in (work.get("referenced_works") or []):
            cited_pub = publications_map.get(ref_id)
            if not cited_pub or cited_pub.id == citing_pub.id:
                continue
            
            key = (citing_pub.id, cited_pub.id)
            if key not in existing:
                from datetime import date
                year = work.get("publication_year")
                citation_date = date(year, 1, 1) if year else None
                
                to_create.append(Citation(
                    citing_publication=citing_pub,
                    cited_publication=cited_pub,
                    source=DataSource.OPENALEX,
                    external_id=ref_id,
                    citation_date=citation_date
                ))
                existing.add(key)
    
    if to_create:
        Citation.objects.bulk_create(to_create, ignore_conflicts=True)
    
    return len(to_create)


# ─────────────────────────────────────────────────────────────────────────────
# 🟢 ÉTAPE 3 : UTILITAIRES
# ─────────────────────────────────────────────────────────────────────────────

def _reconstruct_abstract(inverted_index: Dict) -> str:
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


def _get_first_institution(work: Dict):
    """Récupère la première institution avec country_code:DZ"""
    from institution.models import Institution
    
    for authorship in (work.get("authorships") or []):
        for inst_data in (authorship.get("institutions") or []):
            country_code = inst_data.get("country_code") or ""
            if country_code.upper() == "DZ":
                name = (inst_data.get("display_name") or "").strip()[:200]
                if name:
                    inst = Institution.objects.filter(
                        name__icontains=name[:50]
                    ).first()
                    if inst:
                        return inst
    return None


def _map_contribution(order: int, authorship: Dict) -> int:
    """Map la contribution type (1=first, 2=2nd, 3=3rd, 4=corresponding, 5=other)"""
    if authorship.get("is_corresponding", False):
        return 4
    if order == 1:
        return 1
    if order == 2:
        return 2
    if order == 3:
        return 3
    return 5


# ─────────────────────────────────────────────────────────────────────────────
# 🎯 FONCTION PRINCIPALE
# ─────────────────────────────────────────────────────────────────────────────

def sync_algeria_global(
    start_year: int = 2010, 
    end_year: int = 2025,
    batch_mode: bool = True
) -> Dict:
    """
    🟢 Lance la synchronisation COMPLÈTE pour l'Algérie
    
    1. Fetch OpenAlex (country_code:DZ, publication_year:2010-2025)
    2. Stockage PostgreSQL
    3. Prêt pour Bibliometrix
    
    Paramètres :
    - start_year, end_year : Période à synchroniser
    - batch_mode : Utiliser le mode batch pour les Impact Factors (plus rapide)
    
    Retourne : Statistiques
    """
    
    print(f"\n\n")
    print(f"{'='*70}")
    print(f"  🇩🇿 SYNCHRONISATION GLOBALE ALGÉRIE ({start_year}-{end_year})")
    print(f"  Timestamp: {datetime.now().isoformat()}")
    print(f"  Mode batch: {batch_mode}")
    print(f"{'='*70}")
    
    start_time = time.time()
    
    # ────────────────── ÉTAPE 1 : Fetch ──────────────────
    works = fetch_algeria_publications(start_year, end_year)
    
    if not works:
        print(f"\n  ❌ ERREUR: Aucune publication trouvée")
        return {"status": "failed", "works_fetched": 0}
    
    # ────────────────── ÉTAPE 2 : Stockage ──────────────────
    stats = process_and_store_publications(works)
    
    elapsed = round(time.time() - start_time, 1)
    
    print(f"\n{'='*70}")
    print(f"  ✅ SYNCHRONISATION COMPLÈTE")
    print(f"  ⏱️  Temps total: {elapsed}s")
    print(f"  📊 Statistiques :")
    print(f"     - Publications: {stats['publications_created']} créées, {stats['publications_updated']} MAJ")
    print(f"     - CoAuthors: {stats['coauthors_created']}")
    print(f"     - Citations: {stats['citations_created']}")
    print(f"     - Journaux avec IF: {stats.get('journals_with_if', 0)}")
    print(f"  🎯 Prêt pour Bibliometrix !")
    print(f"{'='*70}\n")
    
    return {
        "status": "success",
        "works_fetched": len(works),
        "elapsed_seconds": elapsed,
        "stats": stats,
    }

# ─────────────────────────────────────────────────────────────────────────────
# 📊 EXPORT BIBLIOMETRIX INTÉGRÉ
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# 📊 EXPORT BIBLIOMETRIX INTÉGRÉ
# ─────────────────────────────────────────────────────────────────────────────

def export_to_bibliometrix_after_sync(
    output_dir: str = "C:\\Users\\ridae\\PFE\\Backend\\outputs",
    include_abstracts: bool = True,
    last_n_years: int = 15
) -> Dict:
    """
    ✅ Exporte automatiquement vers Bibliometrix après synchronisation
    """
    try:
        # ✅ CORRECTION : Utiliser le bon chemin (data_pipeline au lieu de scripts)
        from data_pipeline.export_to_bibliometrix import export_algeria_last_n_years
        
        print(f"\n{'='*70}")
        print(f"  📊 EXPORT BIBLIOMETRIX POST-SYNCHRONISATION")
        print(f"{'='*70}\n")
        
        result = export_algeria_last_n_years(
            output_dir=output_dir,
            n_years=last_n_years,
            include_abstracts=include_abstracts
        )
        
        return result
    except ImportError as e:
        print(f"  ⚠️  Impossible d'importer export_to_bibliometrix: {e}")
        print(f"  💡 Assurez-vous que le fichier data_pipeline/export_to_bibliometrix.py existe")
        return {"status": "failed", "error": str(e)}


def sync_and_export_algeria(
    start_year: int = 2010,
    end_year: int = None,
    auto_export: bool = True,
    export_last_n_years: int = 15,
    output_dir: str = "/mnt/user-data/outputs",
    include_abstracts: bool = True
) -> Dict:
    """
    🚀 SYNCHRONISATION COMPLÈTE + EXPORT BIBLIOMETRIX
    
    Paramètres :
    - start_year, end_year : Période de synchronisation
    - auto_export : Exporter automatiquement après sync
    - export_last_n_years : Nombre d'années pour l'export
    - output_dir : Dossier d'export
    - include_abstracts : Inclure les abstracts dans l'export
    """
    
    # Si end_year non spécifié, utiliser l'année courante
    if end_year is None:
        end_year = datetime.now().year
    
    print(f"\n\n")
    print(f"{'#'*70}")
    print(f"  🚀 SYNC + EXPORT COMPLET ALGÉRIE")
    print(f"  📅 Période sync: {start_year}-{end_year}")
    print(f"  📅 Export: {export_last_n_years} dernières années")
    print(f"{'#'*70}")
    
    # ────────────────── ÉTAPE 1 : Synchronisation ──────────────────
    sync_result = sync_algeria_global(
        start_year=start_year,
        end_year=end_year,
        batch_mode=True
    )
    
    if sync_result["status"] != "success":
        print(f"\n  ❌ Synchronisation échouée, arrêt de l'export")
        return {
            "status": "failed",
            "sync": sync_result,
            "export": None
        }
    
    # ────────────────── ÉTAPE 2 : Export Bibliometrix ──────────────────
    export_result = None
    if auto_export:
        export_result = export_to_bibliometrix_after_sync(
            output_dir=output_dir,
            include_abstracts=include_abstracts,
            last_n_years=export_last_n_years
        )
    
    # ────────────────── RÉSULTAT FINAL ──────────────────
    print(f"\n{'#'*70}")
    print(f"  ✅ PROCESSUS COMPLET TERMINÉ")
    print(f"{'#'*70}")
    print(f"\n  📊 SYNCHRONISATION:")
    print(f"     - Publications: {sync_result['stats']['publications_created']} créées, "
          f"{sync_result['stats']['publications_updated']} mises à jour")
    print(f"     - Co-auteurs: {sync_result['stats']['coauthors_created']}")
    print(f"     - Citations: {sync_result['stats']['citations_created']}")
    
    if export_result and export_result.get("status") == "success":
        print(f"\n  📊 EXPORT BIBLIOMETRIX:")
        print(f"     - Fichier: {export_result['filepath']}")
        print(f"     - Publications exportées: {export_result['count']}")
        print(f"     - Taille: {export_result['file_size_mb']:.2f} MB")
    elif export_result and export_result.get("status") == "failed":
        print(f"\n  ⚠️  EXPORT ÉCHOUÉ: {export_result.get('error', 'Erreur inconnue')}")
    
    print(f"\n{'#'*70}\n")
    
    return {
        "status": "success",
        "sync": sync_result,
        "export": export_result
    }
# Point d'entrée pour exécution directe
if __name__ == "__main__":
    import os
    import sys
    import django

    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.append(BASE_DIR)

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Backend.settings')
    django.setup()
    
    from datetime import date
    current_year = date.today().year
    
    # ============================================================
    # MODE : Sync + Export automatique (RECOMMANDÉ)
    # ============================================================
    result = sync_and_export_algeria(
        start_year=2010,
        end_year=current_year,
        auto_export=True,
        export_last_n_years=15,
        output_dir="C:\\Users\\ridae\\PFE\\Backend\\outputs",
        include_abstracts=True
    )
    
    print(f"\n✅ Résultat final: {result['status']}")
    if result.get('export') and result['export'].get('status') == 'success':
        print(f"📁 Fichier exporté: {result['export']['filepath']}")
        print(f"📊 Publications exportées: {result['export']['count']}")