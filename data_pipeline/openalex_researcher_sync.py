# data_pipeline/openalex_researcher_sync.py
import requests
import time
import logging
import uuid
from django.db import transaction

from citation.models import Citation

logger   = logging.getLogger(__name__)
BASE_URL = "https://api.openalex.org"
HEADERS  = {"User-Agent": "mailto:ridaelaidate7@gmail.com"}


def sync_researcher(orcid: str) -> dict:
    from users.models import Researcher

    try:
        researcher = Researcher.objects.select_related('user').get(orcid=orcid)
    except Researcher.DoesNotExist:
        logger.error(f"Aucun chercheur avec ORCID : {orcid}")
        return {"created": 0, "updated": 0, "errors": 0, "citations": 0}

    print(f"\n{'='*60}")
    print(f"  Sync : {researcher.user.get_full_name()} | ORCID : {orcid}")
    print(f"{'='*60}\n")

    start_time = time.time()

    # ── Récupérer le h-index depuis OpenAlex ──────────────────────────────
    # ── Récupérer le h-index depuis OpenAlex ──────────────────────────────
    try:
        resp = requests.get(
            f"{BASE_URL}/authors/orcid:{orcid}",
            headers=HEADERS,
            timeout=10
        )
        if resp.status_code == 200:
            author_data = resp.json()
            summary     = author_data.get("summary_stats") or {}
            h_index_oa  = summary.get("h_index", 0)
            if h_index_oa:
                researcher.h_index = h_index_oa
                researcher.save(update_fields=["h_index"])
                print(f"   📊 H-index OpenAlex : {h_index_oa}")
    except Exception as e:
        logger.error(f"Erreur fetch h-index: {e}")

    # ── Étape 1 : Fetch publications ──────────────────────────────────────
    works = fetch_works_by_orcid(orcid)
    print(f"✅ {len(works)} publications ({round(time.time()-start_time, 1)}s)\n")

    # ... reste identique
    if not works:
        return {"created": 0, "updated": 0, "errors": 0, "citations": 0}

    stats = {
        "total": len(works), "created": 0, "updated": 0,
        "errors": 0, "coauthors": 0, "citations": 0,
    }

    with transaction.atomic():

        # ── Étape 2 : Journals ────────────────────────────────────────────
        t = time.time()
        journals_map = bulk_get_or_create_journals(works)
        print(f"   📰 Journals  : {len(journals_map)} ({round(time.time()-t, 1)}s)")

        # ── Étape 3 : Keywords ────────────────────────────────────────────
        t = time.time()
        keywords_map = bulk_get_or_create_keywords(works)
        print(f"   🏷️  Keywords  : {len(keywords_map)} ({round(time.time()-t, 1)}s)")

        # ── Étape 4 : Publications ────────────────────────────────────────
        t = time.time()
        openalex_ids = [w.get("id") for w in works if w.get("id")]
        dois = [
            w.get("doi", "").replace("https://doi.org/", "").strip()
            for w in works if w.get("doi")
        ]
        from publication.models import Publication
        existing_by_openalex = {
            p.openalex_id: p
            for p in Publication.objects.filter(openalex_id__in=openalex_ids)
        }
        existing_by_doi = {
            p.doi: p
            for p in Publication.objects.filter(doi__in=dois) if p.doi
        }
        publications_map, pub_stats = bulk_get_or_create_publications(
            works, journals_map, existing_by_openalex, existing_by_doi, researcher
        )
        stats.update({
            "created": pub_stats["created"],
            "updated": pub_stats["updated"],
            "errors":  pub_stats["errors"],
        })
        print(f"   📄 Publications : {pub_stats['created']} créées, "
              f"{pub_stats['updated']} MAJ ({round(time.time()-t, 1)}s)")

        # ── Étape 5 : Keywords M2M ────────────────────────────────────────
        t = time.time()
        bulk_assign_keywords(works, publications_map, keywords_map)
        print(f"   🔗 Keywords assignés ({round(time.time()-t, 1)}s)")

        # ── Étape 6 : CoAuthors ───────────────────────────────────────────
        t = time.time()
        nb = bulk_process_authorships(works, publications_map, researcher)
        stats["coauthors"] = nb
        print(f"   👥 CoAuthors : {nb} ({round(time.time()-t, 1)}s)")

        # ── Étape 7 : Résoudre les références manquantes ──────────────────
        #t = time.time()
        #publications_map = fetch_missing_references(works, publications_map)
        print(f"   🔍 Références résolues ({round(time.time()-t, 1)}s)")

        # ── Étape 8 : Citations ───────────────────────────────────────────
        t = time.time()
        nb = bulk_process_citations(works, publications_map)
        stats["citations"] = nb
        print(f"   🔗 Citations : {nb} ({round(time.time()-t, 1)}s)")
        # ── Étape 9 : Citations ENTRANTES ────────────────────────────────
        #t = time.time()
        nb_in = fetch_incoming_citations(works, publications_map)
        stats["citations_in"] = nb_in
        print(f"   📥 Citations entrantes : {nb_in} ({round(time.time()-t, 1)}s)")

        # ── Étape 10 : Altmetric-like score ───────────────────
        t = time.time()
        compute_altmetric_scores(publications_map)
        print(f"   📊 Altmetric score calculé ({round(time.time()-t, 1)}s)")
        # ── Étape 11 : Impact Factor Journaux ────────────────────────────
        t = time.time()
        fetch_journal_impact_factors()
        print(f"   📰 Impact factors mis à jour ({round(time.time()-t, 1)}s)")
    # ── H-index ───────────────────────────────────────────────────────────
    researcher.refresh_from_db()
    new_h = researcher.h_index
    elapsed = round(time.time() - start_time, 1)

    print(f"\n{'='*60}")
    print(f"  ✅ Sync terminée en {elapsed}s")
    print(f"  Publications : {stats['created']} créées | {stats['updated']} MAJ")
    print(f"  CoAuthors    : {stats['coauthors']}")
    print(f"  Citations    : {stats['citations']}")
    print(f"  H-index      : {new_h}")
    print(f"{'='*60}\n")
    return stats


def sync_all_researchers() -> dict:
    from users.models import Researcher
    researchers = Researcher.objects.filter(
        orcid__isnull=False,
        user__is_active=True
    ).exclude(orcid="").exclude(
        user__email__icontains="external.openalex"
    ).select_related("user")

    print(f"\n🔄 {researchers.count()} chercheur(s) à synchroniser...\n")
    total = {"created": 0, "updated": 0, "citations": 0, "errors": 0}

    for researcher in researchers:
        try:
            stats = sync_researcher(researcher.orcid)
            for key in total:
                total[key] += stats.get(key, 0)
        except Exception as e:
            logger.error(f"Erreur sync {researcher.orcid}: {e}")

    print(f"\n✅ Sync complète — Créées: {total['created']} | "
          f"Citations: {total['citations']}")
    return total


# ─── FETCH ────────────────────────────────────────────────────────────────────

def fetch_works_by_orcid(orcid: str) -> list:
    works    = []
    cursor   = "*"

    while True:
        params = {
            "filter":   f"author.orcid:{orcid}",
            "per-page": 200,
            "cursor":   cursor,
            "select":   ",".join([
                "id", "title", "abstract_inverted_index",
                "publication_year", "doi", "type",
                "cited_by_count", "authorships",
                "primary_location", "concepts",
                "referenced_works",
            ]),
        }
        try:
            resp = requests.get(
                f"{BASE_URL}/works", params=params,
                headers=HEADERS, timeout=20
            )
            resp.raise_for_status()
            data    = resp.json()
            results = data.get("results", [])
            cursor  = data.get("meta", {}).get("next_cursor")
            if not results:
                break
            works += results
            if not cursor:
                break
        except Exception as e:
            logger.error(f"Erreur fetch: {e}")
            break

    return works


# ─── JOURNALS ─────────────────────────────────────────────────────────────────

def bulk_get_or_create_journals(works: list) -> dict:
    from journal.models import Journal

    # Collecter tous les journaux uniques
    journals_info = {}
    for work in works:
        source = (work.get("primary_location") or {}).get("source") or {}
        name   = (source.get("display_name") or "").strip()[:500]
        if not name:
            continue
        issns = source.get("issn") or []
        issn  = issns[0] if issns else None
        key   = issn if issn else name
        journals_info[key] = {"name": name, "issn": issn}

    if not journals_info:
        return {}

    issns = [v["issn"] for v in journals_info.values() if v["issn"]]
    names = [v["name"] for v in journals_info.values() if not v["issn"]]

    existing = {}
    if issns:
        for j in Journal.objects.filter(issn__in=issns):
            existing[j.issn] = j
    if names:
        for j in Journal.objects.filter(name__in=names, issn__isnull=True):
            existing[j.name] = j

    # Créer manquants
    to_create = [
        Journal(name=d["name"], issn=d["issn"])
        for key, d in journals_info.items()
        if key not in existing
    ]
    if to_create:
        Journal.objects.bulk_create(to_create, ignore_conflicts=True)
        if issns:
            for j in Journal.objects.filter(issn__in=issns):
                existing[j.issn] = j
        if names:
            for j in Journal.objects.filter(name__in=names):
                existing[j.name] = j

    # Map openalex_id → Journal
    result = {}
    for work in works:
        source = (work.get("primary_location") or {}).get("source") or {}
        name   = (source.get("display_name") or "").strip()[:500]
        if not name:
            continue
        issns  = source.get("issn") or []
        issn   = issns[0] if issns else None
        key    = issn if issn else name
        oid    = work.get("id", "")
        if oid and key in existing:
            result[oid] = existing[key]

    return result


# ─── KEYWORDS ─────────────────────────────────────────────────────────────────

def bulk_get_or_create_keywords(works: list) -> dict:
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


# ─── PUBLICATIONS ─────────────────────────────────────────────────────────────

def bulk_get_or_create_publications(
    works, journals_map, existing_by_openalex, existing_by_doi, researcher
):
    from publication.models import Publication, PublicationType

    type_map = {
        "journal-article":     PublicationType.ARTICLE,
        "book":                PublicationType.BOOK,
        "proceedings-article": PublicationType.CONFERENCE_PAPER,
        "review-article":      PublicationType.REVIEW,
        "book-chapter":        PublicationType.BOOK,
    }

    publications_map = {}
    to_create        = []
    to_update        = []
    stats            = {"created": 0, "updated": 0, "errors": 0}

    for work in works:
        try:
            title = (work.get("title") or "").strip()
            if not title:
                continue

            oid  = work.get("id", "") or None
            doi  = (work.get("doi") or "").replace("https://doi.org/", "").strip() or None
            abstract = reconstruct_abstract(work.get("abstract_inverted_index") or {})
            pub_type = type_map.get(work.get("type", ""), PublicationType.ARTICLE)
            journal  = journals_map.get(oid)
            inst     = get_institution_of_researcher(work, researcher)

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
                    title            = title[:1000],
                    abstract         = abstract,
                    publication_year = work.get("publication_year"),
                    doi              = doi,
                    openalex_id      = oid,
                    type             = pub_type,
                    journal          = journal,
                    institution      = inst,
                    citation_count   = work.get("cited_by_count", 0),
                    is_validated     = True,
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


# ─── KEYWORDS ASSIGN ──────────────────────────────────────────────────────────

def bulk_assign_keywords(works, publications_map, keywords_map):
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
            kw    = keywords_map.get(label)
            if kw and (pub.id, kw.id) not in existing:
                to_create.append(PublicationKeyword(
                    publication_id=pub.id, keyword_id=kw.id
                ))
                existing.add((pub.id, kw.id))

    if to_create:
        PublicationKeyword.objects.bulk_create(to_create, ignore_conflicts=True)


# ─── COAUTHORS ────────────────────────────────────────────────────────────────

def bulk_process_authorships(works, publications_map, main_researcher) -> int:
    """
    Crée des entrées CoAuthor pour TOUS les auteurs de chaque publication.
    
    Supporte la duplication: un même auteur peut avoir plusieurs entrées dans la même publication
    (ex: premier auteur ET auteur correspondant)
    
    GARANTIE: Chaque publication aura AU MOINS une entrée pour le chercheur principal
    """
    from coAuthor.models import CoAuthor
    from users.models import Researcher
    from django.db import connection, IntegrityError
    from django.db.models import Q
    
    print(f"\n   👥 Début bulk_process_authorships")
    print(f"   📊 Publications à traiter: {len(publications_map)}")
    print(f"   👤 Chercheur principal: {main_researcher.user.get_full_name()} ({main_researcher.orcid})")
    
    # ── Charger les users existants par ORCID ─────────────
    known_users = {
        r.orcid: r.user
        for r in Researcher.objects.select_related('user')
        if r.orcid
    }
    
    # Ajouter le chercheur principal aux known_users
    if main_researcher.orcid and main_researcher.orcid not in known_users:
        known_users[main_researcher.orcid] = main_researcher.user
    
    # ── Charger coauthors existants en base ───────
    pub_ids = [p.id for p in publications_map.values()]
    
    # Récupérer TOUS les CoAuthor existants
    existing_coauthors = CoAuthor.objects.filter(
        publication_id__in=pub_ids
    )
    
    # CRITICAL: Clé qui inclut l'ordre pour permettre la duplication
    # MAIS nous devons aussi vérifier les contraintes UNIQUE
    existing_keys = set()
    for ca in existing_coauthors:
        # Clé de comparaison pour éviter les doublons dans la même session
        if ca.author_orcid:
            key = (ca.publication_id, ca.author_orcid, ca.author_order)
        else:
            identifier = ca.openalex_id or ca.author_name
            key = (ca.publication_id, identifier, ca.author_order)
        existing_keys.add(key)
    
    print(f"   📊 {len(existing_keys)} entrées CoAuthor existantes")
    
    # Afficher les clés existantes pour debug
    if existing_keys:
        print(f"   🔑 Clés existantes (premières):")
        for i, key in enumerate(list(existing_keys)[:5]):
            print(f"      {i+1}. Pub:{key[0]}, Identifier:{key[1][:30] if len(key)>1 else 'None'}, Ordre:{key[2] if len(key)>2 else 'None'}")
    
    coauthors_to_create = []
    stats = {
        "total_created": 0,
        "main_researcher_entries": 0,
        "publications_processed": 0,
        "duplicates_skipped": 0
    }
    
    # Pour debug - afficher les publications
    print(f"\n   📋 Liste des publications à traiter:")
    for i, (oid, pub) in enumerate(publications_map.items(), 1):
        print(f"      {i}. Pub ID:{pub.id} - {pub.title[:50]}...")
    
    for work in works:
        oid = work.get("id", "")
        pub = publications_map.get(oid)
        
        if not pub:
            continue
        
        stats["publications_processed"] += 1
        
        print(f"\n      📄 Publication {stats['publications_processed']} (ID:{pub.id}): {pub.title[:60]}...")
        
        # Suivre les ordres où le chercheur principal a été trouvé
        main_researcher_orders_found = set()
        
        # Parcourir tous les auteurs de la publication
        authors_in_pub = []
        for order, authorship in enumerate(work.get("authorships") or [], start=1):
            
            author = authorship.get("author") or {}
            
            name = (author.get("display_name") or "").strip()
            orcid = (author.get("orcid") or "").replace(
                "https://orcid.org/", ""
            ).strip() or None
            
            openalex_id = author.get("id")
            
            if not name:
                continue
            
            # Affiliation
            inst_list = authorship.get("institutions") or []
            affiliation = inst_list[0].get("display_name", "") if inst_list else ""
            
            # Déterminer l'utilisateur lié
            linked_user = None
            is_main_researcher = False
            
            # Cas 1: C'est le chercheur principal (même ORCID)
            if orcid and orcid == main_researcher.orcid:
                linked_user = main_researcher.user
                is_main_researcher = True
                main_researcher_orders_found.add(order)
                print(f"         🎯 Chercheur principal trouvé (ordre {order}): {name} (ORCID:{orcid})")
            
            # Cas 2: L'auteur a un ORCID connu
            elif orcid and orcid in known_users:
                linked_user = known_users[orcid]
                print(f"         📌 Auteur connu: {name} (ORCID:{orcid})")
            
            # Cas 3: Le nom correspond au chercheur principal (fallback)
            elif name.lower() == main_researcher.user.get_full_name().lower():
                linked_user = main_researcher.user
                is_main_researcher = True
                main_researcher_orders_found.add(order)
                print(f"         🎯 Chercheur principal trouvé par nom (ordre {order}): {name} (sans ORCID)")
            
            # Déterminer le type de contribution
            contribution_type = map_contribution(order, authorship)
            
            # CRITICAL: Clé qui inclut l'ordre pour permettre la duplication
            if orcid:
                key = (pub.id, orcid, order)
            elif openalex_id:
                key = (pub.id, openalex_id, order)
            else:
                key = (pub.id, name, order)
            
            authors_in_pub.append({
                'name': name,
                'orcid': orcid,
                'order': order,
                'key': key,
                'is_main': is_main_researcher
            })
            
            # Vérifier si cette combinaison existe déjà
            if key not in existing_keys:
                coauthor = CoAuthor(
                    publication=pub,
                    author_name=name[:255],
                    author_orcid=orcid,
                    openalex_id=openalex_id,
                    linked_user=linked_user,
                    contribution_type=contribution_type,
                    author_order=order,
                    affiliation_at_time=affiliation[:255],
                )
                coauthors_to_create.append(coauthor)
                existing_keys.add(key)
                
                marker = "🔴 PRINCIPAL" if is_main_researcher else "👤"
                role_text = ""
                if contribution_type == 4:
                    role_text = " (Corresponding)"
                elif contribution_type == 1 and order == 1:
                    role_text = " (First Author)"
                
                print(f"            ➕ {marker}: {name[:40]} (ordre {order}){role_text}")
                
                if is_main_researcher:
                    stats["main_researcher_entries"] += 1
                    print(f"               → Ajouté dans coauthors_to_create (total principal: {stats['main_researcher_entries']})")
            else:
                print(f"            ⏭️  SKIP: {name[:40]} (ordre {order}) - déjà existant dans existing_keys")
                stats["duplicates_skipped"] += 1
                if is_main_researcher:
                    print(f"               → ⚠️  Chercheur principal déjà existant dans existing_keys!")
        
        # Afficher le résumé des auteurs trouvés
        print(f"         📊 Résumé des auteurs: {len(authors_in_pub)} trouvés")
        for auth in authors_in_pub:
            print(f"            - Ordre {auth['order']}: {auth['name']} (main:{auth['is_main']})")
        
        # CRITICAL: Si le chercheur principal n'a été trouvé dans AUCUN ordre
        if not main_researcher_orders_found and main_researcher.orcid:
            print(f"         ⚠️  Chercheur principal non trouvé dans les auteurs!")
            print(f"         🔧 Création d'une entrée par défaut (ordre 0)...")
            
            # Créer une entrée par défaut avec order=0
            key = (pub.id, main_researcher.orcid, 0)
            if key not in existing_keys:
                coauthor = CoAuthor(
                    publication=pub,
                    author_name=main_researcher.user.get_full_name()[:255],
                    author_orcid=main_researcher.orcid,
                    openalex_id=None,
                    linked_user=main_researcher.user,
                    contribution_type=5,  # Other
                    author_order=0,  # Ordre spécial pour "non trouvé"
                    affiliation_at_time="",
                )
                coauthors_to_create.append(coauthor)
                existing_keys.add(key)
                stats["main_researcher_entries"] += 1
                print(f"            ✅ Création forcée: {main_researcher.user.get_full_name()} (ordre 0)")
            else:
                print(f"            ⏭️  Déjà existant")
        elif not main_researcher_orders_found:
            print(f"         ⚠️  Chercheur principal non trouvé ET pas d'ORCID!")
        else:
            print(f"         ✅ Chercheur principal trouvé {len(main_researcher_orders_found)} fois aux ordres {sorted(main_researcher_orders_found)}")
    
    # Afficher le nombre total d'entrées à créer
    print(f"\n   📊 Total à créer: {len(coauthors_to_create)}")
    print(f"      - Dont chercheur principal: {stats['main_researcher_entries']}")
    print(f"      - Doublons ignorés: {stats['duplicates_skipped']}")
    
    # Création en masse
    if coauthors_to_create:
        try:
            # Afficher les premières entrées à créer
            print(f"\n   🔍 Entrées à créer (premières):")
            for i, ca in enumerate(coauthors_to_create[:5]):
                print(f"      {i+1}. Pub:{ca.publication_id} | Ordre:{ca.author_order} | Auteur:{ca.author_name[:30]} | ORCID:{ca.author_orcid}")
            
            # Vérification des contraintes avant création
            # Regarder le modèle CoAuthor pour voir les contraintes uniques
            print(f"   🔍 Vérification des contraintes du modèle CoAuthor...")
            
            # Essayer bulk_create SANS ignore_conflicts pour voir l'erreur exacte
            try:
                result = CoAuthor.objects.bulk_create(coauthors_to_create, ignore_conflicts=False)
                stats["total_created"] = len(result)
                print(f"\n   ✅ {stats['total_created']} CoAuthor créées au total")
            except IntegrityError as e:
                print(f"   ❌ IntegrityError lors de bulk_create: {e}")
                print(f"   🔧 Fallback: création individuelle avec gestion des doublons...")
                
                # Fallback: créer une par une
                created_count = 0
                for ca in coauthors_to_create:
                    try:
                        # Vérifier si existe déjà avec une requête plus précise
                        exists = CoAuthor.objects.filter(
                            publication=ca.publication,
                            author_order=ca.author_order,
                            author_name=ca.author_name
                        ).exists()
                        
                        if ca.author_orcid:
                            exists = exists or CoAuthor.objects.filter(
                                publication=ca.publication,
                                author_orcid=ca.author_orcid,
                                author_order=ca.author_order
                            ).exists()
                        
                        if not exists:
                            ca.save()
                            created_count += 1
                            if created_count % 5 == 0:
                                print(f"      ✅ {created_count}/{len(coauthors_to_create)} créées")
                        else:
                            print(f"      ⏭️  SKIP (existe déjà): {ca.author_name} (pub {ca.publication_id}, ordre {ca.author_order})")
                    except IntegrityError as inner_e:
                        print(f"      ⚠️  IntegrityError pour {ca.author_name}: {inner_e}")
                    except Exception as inner_e:
                        print(f"      ⚠️  Erreur inattendue {ca.author_name}: {inner_e}")
                
                stats["total_created"] = created_count
                print(f"\n   ✅ {created_count} CoAuthor créées individuellement")
            
            print(f"      - Entrées pour le chercheur principal: {stats['main_researcher_entries']}")
            print(f"      - Publications traitées: {stats['publications_processed']}")
            
            # Vérification finale
            expected_min = len(publications_map)  # Au moins une par publication
            if stats['main_researcher_entries'] >= expected_min:
                print(f"      ✅ OK: {stats['main_researcher_entries']} entrées pour le chercheur principal ({expected_min} publications)")
            else:
                print(f"      ⚠️  ATTENTION: Seulement {stats['main_researcher_entries']}/{expected_min} entrées pour le chercheur principal")
                
            # Vérification post-création
            for pub_id in pub_ids:
                count = CoAuthor.objects.filter(publication_id=pub_id).count()
                if count == 0:
                    print(f"      ⚠️  Publication {pub_id} n'a AUCUNE entrée CoAuthor!")
                
                principal_count = CoAuthor.objects.filter(
                    publication_id=pub_id, 
                    author_orcid=main_researcher.orcid
                ).count()
                if principal_count == 0 and stats["main_researcher_entries"] > 0:
                    print(f"      ⚠️  Publication {pub_id} n'a pas d'entrée pour le chercheur principal!")
                        
        except Exception as e:
            print(f"   ❌ Erreur lors de bulk_create: {e}")
            import traceback
            traceback.print_exc()
            print(f"   🔧 Fallback ultime: création individuelle...")
            
            # Fallback ultime: créer une par une
            created_count = 0
            for ca in coauthors_to_create:
                try:
                    # Vérifier si existe déjà
                    if not CoAuthor.objects.filter(
                        publication=ca.publication,
                        author_order=ca.author_order,
                        author_name=ca.author_name
                    ).exists():
                        ca.save()
                        created_count += 1
                        print(f"      ✅ Créé: {ca.author_name} (pub {ca.publication_id}, ordre {ca.author_order})")
                except Exception as inner_e:
                    print(f"      ⚠️  Erreur création {ca.author_name}: {inner_e}")
            
            stats["total_created"] = created_count
            print(f"   ✅ {created_count} CoAuthor créées individuellement")
    else:
        print(f"\n   ℹ️  Aucune nouvelle CoAuthor à créer")
    
    return stats["total_created"]
# ─── CITATIONS ────────────────────────────────────────────────────────────────

def bulk_process_citations(works, publications_map) -> int:
    from citation.models import Citation, DataSource
    from publication.models import Publication
    
    print(f"\n   🔍 DEBUG: Début bulk_process_citations")
    print(f"   📊 publications_map contient {len(publications_map)} publications")
    
    all_ref_ids = set()
    for work in works:
        for ref_id in (work.get("referenced_works") or []):
            all_ref_ids.add(ref_id)
    
    print(f"   📊 {len(all_ref_ids)} références uniques trouvées")
    
    if not all_ref_ids:
        return 0
    
    all_cited = publications_map
    
    # Charger citations existantes
    pub_ids = [p.id for p in publications_map.values() if p.id]
    print(f"   📊 Publications avec ID: {len(pub_ids)}/{len(publications_map)}")
    
    if not pub_ids:
        print(f"   ⚠️  Aucune publication n'a d'ID valide!")
        return 0
    
    existing = set(
        Citation.objects.filter(
            citing_publication_id__in=pub_ids
        ).values_list('citing_publication_id', 'cited_publication_id')
    )
    print(f"   📊 Citations existantes: {len(existing)}")
    
    to_create = []
    for work in works:
        oid = work.get("id", "")
        citing_pub = publications_map.get(oid)
        if not citing_pub:
            continue
        
        for ref_id in (work.get("referenced_works") or []):
            cited_pub = all_cited.get(ref_id)
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
    
    print(f"   📊 Citations à créer: {len(to_create)}")
    
    if to_create:
        try:
            # Vérifier les IDs avant création
            for i, cit in enumerate(to_create[:5]):  # Afficher les 5 premiers
                print(f"      - Citation {i+1}: citing_id={cit.citing_publication_id}, cited_id={cit.cited_publication_id}")
            
            # Essayer la création
            result = Citation.objects.bulk_create(to_create, ignore_conflicts=True)
            print(f"   ✅ {len(result)} citations créées avec succès")
            return len(result)
        except Exception as e:
            print(f"   ❌ Erreur lors de bulk_create: {e}")
            import traceback
            traceback.print_exc()
            return 0
    else:
        print(f"   ⚠️  Aucune citation à créer")
        return 0


# ─── UTILITAIRES ──────────────────────────────────────────────────────────────

def get_institution_of_researcher(work: dict, researcher):
    from institution.models import Institution

    for authorship in (work.get("authorships") or []):
        author_orcid = (
            (authorship.get("author") or {}).get("orcid") or ""
        ).replace("https://orcid.org/", "").strip()

        if author_orcid != researcher.orcid:
            continue

        for inst_data in (authorship.get("institutions") or []):
            name = (inst_data.get("display_name") or "").strip()[:200]
            if not name:
                continue
            inst = Institution.objects.filter(
                name__icontains=name[:50]
            ).first()
            if inst:
                return inst
    return None


def reconstruct_abstract(inverted_index: dict) -> str:
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


def map_contribution(order: int, authorship: dict) -> int:
    if authorship.get("is_corresponding", False):
        return 4
    if order == 1: return 1
    if order == 2: return 2
    if order == 3: return 3
    return 5
def fetch_missing_references(works: list, publications_map: dict) -> dict:
    """
    Récupère depuis OpenAlex les publications référencées
    qui ne sont pas encore en base et les crée de façon minimale.
    """
    from publication.models import Publication, PublicationType
    from journal.models import Journal

    # 1. Collecter tous les IDs référencés
    all_ref_ids = set()
    for work in works:
        for ref_id in (work.get("referenced_works") or []):
            all_ref_ids.add(ref_id)

    if not all_ref_ids:
        return publications_map

    # 2. Identifier ceux qui manquent
    existing_oids = set(
        Publication.objects.filter(
            openalex_id__in=all_ref_ids
        ).values_list('openalex_id', flat=True)
    )
    existing_in_map = set(publications_map.keys())
    missing_ids     = all_ref_ids - existing_oids - existing_in_map

    print(f"   🔍 {len(missing_ids)} références manquantes sur {len(all_ref_ids)} total")

    if not missing_ids:
        # Charger celles déjà en base dans le map
        for pub in Publication.objects.filter(openalex_id__in=all_ref_ids):
            publications_map[pub.openalex_id] = pub
        return publications_map

    # 3. Récupérer par batch de 50 depuis OpenAlex
    missing_list  = list(missing_ids)
    batch_size    = 50
    created_count = 0

    type_map = {
        "journal-article":     PublicationType.ARTICLE,
        "book":                PublicationType.BOOK,
        "proceedings-article": PublicationType.CONFERENCE_PAPER,
        "review-article":      PublicationType.REVIEW,
        "book-chapter":        PublicationType.BOOK,
    }

    for i in range(0, len(missing_list), batch_size):
        batch = missing_list[i:i + batch_size]
        try:
            ids_filter = "|".join(batch)
            resp = requests.get(
                f"{BASE_URL}/works",
                params={
                    "filter":   f"openalex_id:{ids_filter}",
                    "per-page": batch_size,
                    "select":   "id,title,publication_year,doi,type,"
                                "cited_by_count,primary_location",
                },
                headers=HEADERS,
                timeout=20
            )
            resp.raise_for_status()
            ref_works = resp.json().get("results", [])

            to_create = []
            for ref_work in ref_works:
                oid   = ref_work.get("id", "")
                title = (ref_work.get("title") or "").strip()[:1000]
                doi   = (ref_work.get("doi") or "").replace(
                    "https://doi.org/", ""
                ).strip() or None

                if not title or not oid:
                    continue

                # Journal minimal
                journal = None
                source  = (ref_work.get("primary_location") or {}).get("source") or {}
                j_name  = (source.get("display_name") or "").strip()[:500]
                if j_name:
                    issns  = source.get("issn") or []
                    issn   = issns[0] if issns else None
                    if issn:
                        journal, _ = Journal.objects.get_or_create(
                            issn=issn, defaults={"name": j_name}
                        )
                    else:
                        journal, _ = Journal.objects.get_or_create(
                            name=j_name, defaults={"issn": None}
                        )

                to_create.append(Publication(
                    title            = title,
                    publication_year = ref_work.get("publication_year"),
                    doi              = doi,
                    openalex_id      = oid,
                    type             = type_map.get(
                        ref_work.get("type", ""), PublicationType.ARTICLE
                    ),
                    journal          = journal,
                    citation_count   = ref_work.get("cited_by_count", 0),
                    is_validated     = True,
                ))

            if to_create:
                Publication.objects.bulk_create(
                    to_create, ignore_conflicts=True
                )
                created_count += len(to_create)

            time.sleep(0.1)

        except Exception as e:
            logger.error(f"Erreur fetch références batch {i}: {e}")
            continue

    print(f"   ✅ {created_count} publications référencées créées")

    # 4. Charger toutes dans le map
    for pub in Publication.objects.filter(openalex_id__in=all_ref_ids):
        publications_map[pub.openalex_id] = pub

    return publications_map
def fetch_incoming_citations(works: list, publications_map: dict) -> int:
    """
    Récupère depuis OpenAlex les publications qui CITENT
    les publications du chercheur (citations entrantes).
    Les crée en base et crée les liens Citation.
    """
    from publication.models import Publication, PublicationType
    from citation.models import Citation, DataSource
    from journal.models import Journal

    if not publications_map:
        return 0

    type_map = {
        "journal-article":     PublicationType.ARTICLE,
        "book":                PublicationType.BOOK,
        "proceedings-article": PublicationType.CONFERENCE_PAPER,
        "review-article":      PublicationType.REVIEW,
        "book-chapter":        PublicationType.BOOK,
    }

    total_created = 0

    for work in works:
        oid       = work.get("id", "")
        cited_pub = publications_map.get(oid)
        if not cited_pub:
            continue

        # Pas besoin de chercher si cited_by_count = 0
        if not work.get("cited_by_count", 0):
            continue

        print(f"      🔎 Fetch citations entrantes pour : {cited_pub.title[:50]}")

        # Récupérer les publications qui citent cette publication
        citing_works = []
        cursor = "*"

        while True:
            try:
                resp = requests.get(
                    f"{BASE_URL}/works",
                    params={
                        "filter":   f"cites:{oid}",
                        "per-page": 50,
                        "cursor":   cursor,
                        "select":   "id,title,publication_year,doi,type,"
                                    "cited_by_count,primary_location",
                    },
                    headers=HEADERS,
                    timeout=20
                )
                resp.raise_for_status()
                data    = resp.json()
                results = data.get("results", [])
                cursor  = data.get("meta", {}).get("next_cursor")
                citing_works += results
                if not results or not cursor:
                    break
            except Exception as e:
                logger.error(f"Erreur fetch citations entrantes {oid}: {e}")
                break

        if not citing_works:
            continue

        print(f"         → {len(citing_works)} publications trouvées")

        # Vérifier lesquelles existent déjà en base
        citing_oids = [w.get("id") for w in citing_works if w.get("id")]
        existing_pubs = {
            p.openalex_id: p
            for p in Publication.objects.filter(openalex_id__in=citing_oids)
        }

        # Créer les publications manquantes
        to_create = []
        for citing_work in citing_works:
            c_oid  = citing_work.get("id", "")
            if not c_oid or c_oid in existing_pubs:
                continue

            title = (citing_work.get("title") or "").strip()[:1000]
            doi   = (citing_work.get("doi") or "").replace(
                "https://doi.org/", ""
            ).strip() or None

            if not title:
                continue

            # Journal minimal
            journal = None
            source  = (citing_work.get("primary_location") or {}).get("source") or {}
            j_name  = (source.get("display_name") or "").strip()[:500]
            if j_name:
                issns = source.get("issn") or []
                issn  = issns[0] if issns else None
                if issn:
                    journal, _ = Journal.objects.get_or_create(
                        issn=issn, defaults={"name": j_name}
                    )
                else:
                    journal, _ = Journal.objects.get_or_create(
                        name=j_name, defaults={"issn": None}
                    )

            to_create.append(Publication(
                title            = title,
                publication_year = citing_work.get("publication_year"),
                doi              = doi,
                openalex_id      = c_oid,
                type             = type_map.get(
                    citing_work.get("type", ""), PublicationType.ARTICLE
                ),
                journal          = journal,
                citation_count   = citing_work.get("cited_by_count", 0),
                is_validated     = True,
            ))

        if to_create:
            Publication.objects.bulk_create(to_create, ignore_conflicts=True)

        # Recharger toutes les publications citing depuis la DB
        all_citing_pubs = {
            p.openalex_id: p
            for p in Publication.objects.filter(openalex_id__in=citing_oids)
        }

        # Charger citations entrantes existantes pour cette pub
        existing_citations = set(
            Citation.objects.filter(
                cited_publication=cited_pub
            ).values_list('citing_publication_id', flat=True)
        )

        # Créer les liens Citation
        citations_to_create = []
        for citing_work in citing_works:
            c_oid      = citing_work.get("id", "")
            citing_pub = all_citing_pubs.get(c_oid)
            if not citing_pub:
                continue
            if citing_pub.id in existing_citations:
                continue
            if citing_pub.id == cited_pub.id:
                continue

            from datetime import date

            year = citing_work.get("publication_year")

            citation_date = None
            if year:
                citation_date = date(year, 1, 1)

            citations_to_create.append(
                Citation(
                    citing_publication=citing_pub,
                    cited_publication=cited_pub,
                    source=DataSource.OPENALEX,
                    external_id=c_oid,
                    citation_date=citation_date
                )
            )
            existing_citations.add(citing_pub.id)

        if citations_to_create:
            Citation.objects.bulk_create(
                citations_to_create, ignore_conflicts=True
            )
            total_created += len(citations_to_create)

        time.sleep(0.2)

    return total_created

def compute_altmetric_scores(publications_map: dict):
    """
    Calcul d'un score d'impact basé sur
    citations + keywords + coauthors
    (optimisé SQL)
    """
    from coAuthor.models import CoAuthor
    from publication.models import Publication

    pubs = list(publications_map.values())
    if not pubs:
        return

    pub_ids = [p.id for p in pubs]

    # ── compter coauthors ──
    coauthor_counts = {}
    for pub_id in (
    CoAuthor.objects
    .filter(publication_id__in=pub_ids)
    .values_list("publication_id", flat=True)
):
     coauthor_counts[pub_id] = coauthor_counts.get(pub_id, 0) + 1
    # ── compter keywords ──
    keyword_counts = {}
    through = Publication.keywords.through

    for pub_id in (
    through.objects
    .filter(publication_id__in=pub_ids)
    .values_list("publication_id", flat=True)
):
     keyword_counts[pub_id] = keyword_counts.get(pub_id, 0) + 1
    to_update = []

    for pub in pubs:

        citations = pub.citation_count or 0
        keywords  = keyword_counts.get(pub.id, 0)
        coauthors = coauthor_counts.get(pub.id, 0)

        score = (
            citations * 0.6 +
            keywords  * 0.2 +
            coauthors * 0.2
        )

        pub.altmetric_score = round(score, 2)
        to_update.append(pub)

    if to_update:
        Publication.objects.bulk_update(to_update, ["altmetric_score"])



def fetch_journal_impact_factors():
    """
    Met à jour les impact factors des journaux depuis OpenAlex.
    OpenAlex fournit cite_score comme alternative à l'impact factor.
    """
    from journal.models import Journal

    journals = Journal.objects.filter(
        issn__isnull=False
    ).exclude(issn="")

    print(f"\n📰 Mise à jour impact factor pour {journals.count()} journaux...")

    to_update = []
    updated   = 0

    for journal in journals:
        try:
            resp = requests.get(
                f"{BASE_URL}/sources",
                params={
                    "filter": f"issn:{journal.issn}",
                    "select": "id,display_name,issn_l,issn,"
                              "summary_stats,apc_usd,is_in_doaj,"
                              "is_core,works_count,cited_by_count",
                },
                headers=HEADERS,
                timeout=10
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])

            if not results:
                continue

            source       = results[0]
            summary      = source.get("summary_stats") or {}

            # cite_score = alternative à l'impact factor
            cite_score   = summary.get("2yr_mean_citedness", 0) or 0
            h_index      = summary.get("h_index", 0) or 0
            i10_index    = summary.get("i10_index", 0) or 0

            if cite_score:
                journal.impact_factor = round(float(cite_score), 3)
                to_update.append(journal)
                updated += 1
                print(f"  ✅ {journal.name[:40]:<40} | IF:{cite_score:.3f}")
            else:
                print(f"  ❌ {journal.name[:40]:<40} | IF: non disponible")

            time.sleep(0.1)

        except Exception as e:
            logger.error(f"Erreur IF journal {journal.issn}: {e}")
            continue

    if to_update:
        Journal.objects.bulk_update(to_update, ["impact_factor"])

    print(f"\n✅ {updated} journaux mis à jour sur {journals.count()}")
    return updated

def fetch_journal_impact_factors_for_journals(journals_list):
    """
    Met à jour les impact factors UNIQUEMENT pour les journaux fournis.
    """
    from journal.models import Journal
    
    if not journals_list:
        return 0
    
    # Filtrer les journaux avec ISSN
    journals_to_update = [j for j in journals_list if j and j.issn]
    
    if not journals_to_update:
        return 0
    
    print(f"\n📰 Mise à jour impact factor pour {len(journals_to_update)} journaux...")
    
    to_update = []
    updated = 0
    
    for journal in journals_to_update:
        try:
            resp = requests.get(
                f"{BASE_URL}/sources",
                params={
                    "filter": f"issn:{journal.issn}",
                    "select": "id,display_name,issn_l,issn,summary_stats",
                },
                headers=HEADERS,
                timeout=10
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            
            if not results:
                continue
            
            source = results[0]
            summary = source.get("summary_stats") or {}
            cite_score = summary.get("2yr_mean_citedness", 0) or 0
            
            if cite_score:
                journal.impact_factor = round(float(cite_score), 3)
                to_update.append(journal)
                updated += 1
                print(f"  ✅ {journal.name[:40]:<40} | IF:{cite_score:.3f}")
            else:
                print(f"  ❌ {journal.name[:40]:<40} | IF: non disponible")
            
            time.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Erreur IF journal {journal.issn}: {e}")
            continue
    
    if to_update:
        Journal.objects.bulk_update(to_update, ["impact_factor"])
    
    print(f"\n✅ {updated} journaux mis à jour")
    return updated



def fix_missing_coauthor_entries(orcid: str) -> dict:
    """
    Corrige les publications manquantes d'un chercheur en créant
    les entrées CoAuthor nécessaires.
    """
    from users.models import Researcher
    from publication.models import Publication
    from coAuthor.models import CoAuthor
    from django.db.models import Q
    
    try:
        researcher = Researcher.objects.select_related('user').get(orcid=orcid)
    except Researcher.DoesNotExist:
        logger.error(f"Aucun chercheur avec ORCID : {orcid}")
        return {"fixed": 0, "errors": 0}
    
    print(f"\n{'='*60}")
    print(f"  Correction CoAuthor pour : {researcher.user.get_full_name()} | ORCID : {orcid}")
    print(f"{'='*60}\n")
    
    # Récupérer toutes les publications du chercheur depuis OpenAlex
    works = fetch_works_by_orcid(orcid)
    
    if not works:
        return {"fixed": 0, "errors": 0}
    
    fixed_count = 0
    
    for work in works:
        oid = work.get("id", "")
        
        # Trouver la publication correspondante en base
        pub = Publication.objects.filter(openalex_id=oid).first()
        
        if not pub:
            continue
        
        # Vérifier si une entrée CoAuthor existe déjà pour ce chercheur
        existing = CoAuthor.objects.filter(
            publication=pub
        ).filter(
            Q(linked_user=researcher.user) | Q(author_orcid=researcher.orcid)
        ).exists()
        
        if not existing:
            # Trouver les informations de l'auteur dans le work
            for authorship in work.get("authorships") or []:
                author = authorship.get("author") or {}
                author_orcid = (author.get("orcid") or "").replace("https://orcid.org/", "").strip()
                
                # Si c'est le chercheur principal
                if author_orcid == researcher.orcid:
                    name = author.get("display_name") or researcher.user.get_full_name()
                    order = 1  # Par défaut
                    contribution_type = 1  # 1 = premier auteur
                    
                    # Trouver l'ordre et la contribution
                    for idx, auth in enumerate(work.get("authorships") or [], start=1):
                        if auth.get("author", {}).get("orcid") == f"https://orcid.org/{researcher.orcid}":
                            order = idx
                            contribution_type = map_contribution(idx, auth)
                            break
                    
                    # Créer l'entrée CoAuthor
                    CoAuthor.objects.create(
                        publication=pub,
                        author_name=name[:255],
                        author_orcid=researcher.orcid,
                        openalex_id=author.get("id"),
                        linked_user=researcher.user,
                        contribution_type=contribution_type,
                        author_order=order,
                        affiliation_at_time="",
                    )
                    fixed_count += 1
                    print(f"  ✅ Ajouté: {pub.title[:60]}... (Ordre: {order})")
                    break
    
    print(f"\n✅ {fixed_count} entrées CoAuthor créées")
    return {"fixed": fixed_count, "errors": 0}


def fix_all_missing_coauthor_entries() -> dict:
    """
    Corrige les entrées CoAuthor manquantes pour tous les chercheurs.
    """
    from users.models import Researcher
    
    researchers = Researcher.objects.filter(
        orcid__isnull=False,
        user__is_active=True
    ).exclude(orcid="")
    
    print(f"\n🔄 Correction CoAuthor pour {researchers.count()} chercheur(s)...\n")
    total = {"fixed": 0, "errors": 0}
    
    for researcher in researchers:
        try:
            stats = fix_missing_coauthor_entries(researcher.orcid)
            total["fixed"] += stats.get("fixed", 0)
            total["errors"] += stats.get("errors", 0)
        except Exception as e:
            logger.error(f"Erreur correction {researcher.orcid}: {e}")
            total["errors"] += 1
    
    print(f"\n✅ Correction terminée — {total['fixed']} entrées CoAuthor créées")
    return total