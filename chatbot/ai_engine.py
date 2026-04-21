"""
ai_engine.py — Moteur de traitement des questions du chatbot
Supporte le français et l'anglais, singulier ET pluriel.
"""
import re
from .semantic_search import semantic_search
from .clustering import cluster_publications
from .services import (
    best_journal,
    best_researcher,
    best_publication,
    best_keyword,
    highest_cited_publications,
    search_publications,
    publications_by_year,
    publications_by_journal,
    recent_publications,
    publication_detail,
    top_researchers,
    researcher_publications,
    researcher_stats,
    citation_stats,
    citations_of_publication,
    top_journals,
    journal_detail,
    top_keywords,
    publications_by_keyword,
    general_stats,
    coauthors_of_researcher,
)


# ─── TABLE DE NORMALISATION ───────────────────────────────────────────────────
# Convertit pluriel → singulier et variantes → forme canonique
# pour que detect_intent n'ait à tester qu'une seule forme

NORMALIZATIONS = [
    # ── Chercheurs ──────────────────────────────────────────────────────
    (r'\bchercheurs\b',           'chercheur'),
    (r'\bchercheuses\b',          'chercheur'),
    (r'\bchercheuse\b',           'chercheur'),
    (r'\bauteurs\b',              'auteur'),
    (r'\bautrices\b',             'auteur'),
    (r'\bresearchers\b',          'researcher'),
    (r'\bauthors\b',              'author'),
    (r'\bscientists\b',           'researcher'),
    (r'\bscientist\b',            'researcher'),

    # ── Publications ────────────────────────────────────────────────────
    (r'\bpublications\b',         'publication'),
    (r'\barticles\b',             'article'),
    (r'\bpapers\b',               'paper'),
    (r'\btravaux\b',              'travail'),
    (r'\boutputs\b',              'publication'),
    (r'\bworks\b',                'publication'),
    (r'\bœuvres\b',               'publication'),

    # ── Citations ────────────────────────────────────────────────────────
    (r'\bcitations\b',            'citation'),
    (r'\bréférences\b',           'référence'),
    (r'\breferences\b',           'référence'),

    # ── Journaux ────────────────────────────────────────────────────────
    (r'\bjournaux\b',             'journal'),
    (r'\brevues\b',               'revue'),
    (r'\bjournals\b',             'journal'),
    (r'\bmagazines\b',            'magazine'),
    (r'\bperiodicals\b',          'journal'),

    # ── Keywords ─────────────────────────────────────────────────────────
    (r'\bmots-clés\b',            'mot-clé'),
    (r'\bmots clés\b',            'mot-clé'),
    (r'\bkeywords\b',             'keyword'),
    (r'\bthèmes\b',               'thème'),
    (r'\bthemes\b',               'theme'),
    (r'\bdomaines\b',             'domaine'),
    (r'\bsujets\b',               'sujet'),
    (r'\btopics\b',               'topic'),

    # ── Statistiques ─────────────────────────────────────────────────────
    (r'\bstatistiques\b',         'statistique'),
    (r'\bstats\b',                'statistique'),
    (r'\bstatistics\b',           'statistique'),

    # ── Adjectifs qualificatifs (pluriel → singulier) ────────────────────
    (r'\bmeilleurs\b',            'meilleur'),
    (r'\bmeilleures\b',           'meilleur'),
    (r'\bderniers\b',             'dernier'),
    (r'\bdernières\b',            'dernier'),
    (r'\brécents\b',              'récent'),
    (r'\brécentes\b',             'récent'),
    (r'\bplus cités\b',           'plus cité'),
    (r'\bplus citées\b',          'plus cité'),
    (r'\bcités\b',                'cité'),
    (r'\bcitées\b',               'cité'),
    (r'\bcitéd\b',                'cité'),
    (r'\bhighest\b',              'high'),
    (r'\bbest\b',                 'top'),
    (r'\bpopulaires\b',           'populaire'),
    (r'\bactifs\b',               'actif'),
    (r'\bactives\b',              'actif'),
    (r'\bproductifs\b',           'productif'),

    # ── Verbes / conjugaisons ─────────────────────────────────────────────
    (r'\bont publié\b',           'a publié'),
    (r'\bpublient\b',             'publie'),
    (r'\bpubliées\b',             'publié'),
    (r'\bpubliés\b',              'publié'),
    (r'\bsont cités\b',           'est cité'),
    (r'\bsont citées\b',          'est cité'),
]


def normalize(text: str) -> str:
    """
    Normalise le texte :
    1. Minuscules
    2. Pluriel → singulier
    3. Variantes → forme canonique
    """
    t = text.lower().strip()
    for pattern, replacement in NORMALIZATIONS:
        t = re.sub(pattern, replacement, t)
    return t


# ─── EXTRACTEURS ──────────────────────────────────────────────────────────────

def extract_after(original: str, triggers: list) -> str:
    """
    Extrait le texte après le premier trigger trouvé.
    Utilise la question originale (casse préservée) pour l'extraction.
    """
    q = original.lower()
    for trigger in sorted(triggers, key=len, reverse=True):  # plus long d'abord
        if trigger in q:
            idx  = q.find(trigger) + len(trigger)
            name = original[idx:].strip().strip("?").strip(".").strip()
            if name:
                return name
    return ""


# ─── INTENT DETECTION ─────────────────────────────────────────────────────────

def detect_intent(question: str) -> dict:
    """
    Détecte l'intention.
    - q  = texte original en minuscules (pour extractions avec casse)
    - qn = texte normalisé singulier (pour détection d'intention)
    """
    q  = question.lower().strip()
    qn = normalize(question)

    # ══════════════════════════════════════════════════════════════════════
    # 0. AIDE
    # ══════════════════════════════════════════════════════════════════════
    if any(k in qn for k in [
        "help", "aide", "que peux-tu", "what can you",
        "fonctionnalité", "comment utiliser", "how to use",
        "capabilities", "que sais-tu faire", "tu peux faire quoi",
        "quoi faire", "what do you do",
    ]):
        return {"intent": "help"}

    # ══════════════════════════════════════════════════════════════════════
    # 1. CHERCHEURS — avant publications pour éviter conflits
    # ══════════════════════════════════════════════════════════════════════

    # ── Publications D'UN chercheur spécifique ────────────────────────────
    r_pub_triggers = [
        "publications of", "papers by", "publications de",
        "travaux de", "article de", "a publié", "published by",
        "par le chercheur", "work of", "work by",
        "les publications de", "publication du chercheur",
        "publication de", "paper of", "paper by",
    ]
    if any(k in qn for k in r_pub_triggers):
        name = extract_after(question, r_pub_triggers)
        if name:
            return {"intent": "researcher_publications", "name": name}

    # ── Stats D'UN chercheur spécifique ──────────────────────────────────
    r_stats_triggers = [
        "statistique of", "statistique de", "stats of", "stats de",
        "profile of", "profil de", "résumé de", "summary of",
        "bilan de", "rapport de", "fiche de", "données de",
        "info de", "information de",
    ]
    if any(k in qn for k in r_stats_triggers):
        name = extract_after(question, r_stats_triggers)
        if name:
            return {"intent": "researcher_stats", "name": name}

    # ── Co-auteurs D'UN chercheur spécifique ──────────────────────────────
    co_triggers = [
        "coauthor of", "co-author of", "co-auteur de",
        "collaborateur de", "collaborateurs de",
        "works with", "travaille avec",
        "collabore avec", "qui collabore avec",
        "partenaire de", "collègue de",
    ]
    if any(k in qn for k in [
        "coauthor", "co-author", "co-auteur", "collaborat",
        "partenaire", "collègue",
    ]):
        name = extract_after(question, co_triggers)
        if name:
            return {"intent": "coauthors", "name": name}
        # Sans nom → liste des top chercheurs
        return {"intent": "top_researchers"}

    # ── MEILLEUR chercheur (singulier) → 1 résultat ─────────────────────
    if any(k in qn for k in [
        "top researcher", "top chercheur",
        "meilleur researcher", "meilleur chercheur",
        "meilleur auteur", "top auteur",
        "h-index", "h_index",
        "le meilleur chercheur", "quel chercheur",
        "premier chercheur",
    ]) and not any(k in q for k in [
        "researchers", "chercheurs", "auteurs",
        "liste", "list", "classement", "top 5", "top 10",
    ]):
        return {"intent": "best_researcher"}

    # ── TOP chercheurs (pluriel) → liste ─────────────────────────────────
    if any(k in qn for k in [
        "top researcher", "top chercheur",
        "meilleur researcher", "meilleur chercheur",
        "meilleur auteur", "top auteur",
        "best researcher", "best author",
        "h-index", "h_index",
        "qui publie le plus", "chercheur actif",
        "most productive", "most cited researcher",
        "liste chercheur", "liste des chercheur",
        "liste researcher",
    ]):
        return {"intent": "top_researchers"}

    # ══════════════════════════════════════════════════════════════════════
    # 2. PUBLICATIONS
    # ══════════════════════════════════════════════════════════════════════

    # ── MEILLEURE publication (singulier) → 1 résultat ─────────────────
    if any(k in qn for k in [
        "top publication", "meilleur publication",
        "best paper", "best publication",
        "le plus cité", "la plus citée",
        "la meilleur publication",
    ]) and not any(k in q for k in [
        "publications", "papers", "articles",
        "liste", "list", "top 5", "top 10",
    ]):
        return {"intent": "best_publication"}

    # ── Publications les plus citées (pluriel) → liste ───────────────────
    if any(k in qn for k in [
        "high cited", "most cited", "plus cité",
        "top publication", "meilleur publication",
        "best paper", "best publication",
        "publication les plus", "les plus cité",
        "most popular", "most referenced",
        "plus populaire", "plus référencé",
        "le plus cité", "la plus citée",
    ]):
        return {"intent": "highest_cited"}

    # ── Récentes ──────────────────────────────────────────────────────────
    if any(k in qn for k in [
        "recent", "récent",
        "latest", "dernier publication",
        "nouvelle publication", "new publication",
        "dernière publication", "dernier paper",
        "last publication", "most recent",
    ]):
        return {"intent": "recent_publications"}

    # ── Par ANNÉE ─────────────────────────────────────────────────────────
    year_match = re.search(r'\b(19|20)\d{2}\b', q)
    if year_match and any(k in qn for k in [
        "publication", "paper", "article",
        "travail", "en ", "année", "year", "work",
    ]):
        return {"intent": "publications_by_year", "year": int(year_match.group())}

    # ── Par JOURNAL ───────────────────────────────────────────────────────
    j_pub_triggers = [
        "publications dans", "publications in",
        "papers in", "articles dans", "articles in",
        "publié dans", "published in",
        "paru dans", "appeared in",
        "publication dans", "publication in",
    ]
    if any(k in qn for k in j_pub_triggers):
        jname = extract_after(question, j_pub_triggers)
        if jname:
            return {"intent": "publications_by_journal", "journal": jname}

    # ── Par KEYWORD ───────────────────────────────────────────────────────
    kw_pub_triggers = [
        "publications sur", "publications about",
        "papers about", "papers on",
        "articles sur", "sur le thème",
        "about the topic", "recherche sur",
        "works about", "publication sur",
        "paper sur", "paper about",
    ]
    if any(k in qn for k in kw_pub_triggers):
        kw = extract_after(question, kw_pub_triggers)
        if kw and len(kw) > 2:
            return {"intent": "publications_by_keyword", "keyword": kw}

    # ══════════════════════════════════════════════════════════════════════
    # 3. CITATIONS
    # ══════════════════════════════════════════════════════════════════════

    # ── Citations D'UNE publication ───────────────────────────────────────
    cit_pub_triggers = [
        "citation of", "citation de",
        "cited by", "citée par", "cité par",
        "référence of", "référence de",
        "qui cite", "who cites",
        "combien de fois cité",
    ]
    if any(k in qn for k in cit_pub_triggers):
        title = extract_after(question, cit_pub_triggers)
        if title:
            return {"intent": "citations_of_pub", "title": title}

    # ── Statistiques globales des citations ───────────────────────────────
    if any(k in qn for k in [
        "statistique citation", "citation statistique",
        "citation overview", "combien de citation",
        "nombre de citation", "total citation",
        "citation count", "how many citation",
        "citation stat",
    ]):
        return {"intent": "citation_stats"}

    # ══════════════════════════════════════════════════════════════════════
    # 4. JOURNAUX
    # ══════════════════════════════════════════════════════════════════════

    # ── Détail D'UN journal ───────────────────────────────────────────────
    jd_triggers = [
        "journal de", "journal of", "revue de",
        "détail journal", "detail journal",
        "info journal", "information journal",
        "impact factor", "facteur d'impact",
    ]
    if any(k in qn for k in jd_triggers):
        jname = extract_after(question, jd_triggers)
        if jname:
            return {"intent": "journal_detail", "name": jname}

    # ── MEILLEUR journal (singulier) → 1 résultat ────────────────────────
    if any(k in qn for k in [
        "top journal", "meilleur journal",
        "meilleur revue", "le meilleur journal",
        "quel journal", "which journal",
        "premier journal",
    ]) and not any(k in q for k in [
        "journals", "journaux", "revues",
        "liste", "list", "classement", "top 5", "top 10",
    ]):
        return {"intent": "best_journal"}

    # ── TOP journaux (pluriel) → liste ───────────────────────────────────
    if any(k in qn for k in [
        "top journal", "meilleur journal",
        "meilleur revue", "liste journal",
        "liste revue", "liste des journal",
        "journal list", "revue list",
        "classement journal",
    ]):
        return {"intent": "top_journals"}

    # ══════════════════════════════════════════════════════════════════════
    # 5. KEYWORDS / THÈMES
    # ══════════════════════════════════════════════════════════════════════

    # ── Publications par keyword SPÉCIFIQUE ──────────────────────────────
    kw_specific_triggers = [
        "keyword ", "mot-clé ", "thème ",
        "topic ", "domaine ", "sujet ",
    ]
    if any(k in qn for k in kw_specific_triggers):
        kw = extract_after(question, kw_specific_triggers)
        if kw and len(kw) > 2:
            return {"intent": "publications_by_keyword", "keyword": kw}

    # ── MEILLEUR keyword (singulier) → 1 résultat ───────────────────────
    if any(k in qn for k in [
        "top keyword", "top mot-clé", "top thème",
        "le mot-clé principal", "le thème principal",
        "premier keyword", "premier mot-clé",
    ]) and not any(k in q for k in [
        "keywords", "mots-clés", "thèmes",
        "liste", "list", "tous",
    ]):
        return {"intent": "best_keyword"}

    # ── Liste des keywords (pluriel) → liste ─────────────────────────────
    if any(k in qn for k in [
        "top keyword", "top mot-clé", "top thème",
        "liste keyword", "liste mot-clé",
        "liste des keyword", "liste des mot-clé",
        "keyword list", "tous les keyword",
        "fréquent keyword", "keyword fréquent",
        "les mot-clé", "tous les thème",
    ]):
        return {"intent": "top_keywords"}

    # ── Clusters / Regroupements thématiques ─────────────────────────────
    if any(k in qn for k in [
        "cluster", "group", "regroupement",
        "catégorie", "research cluster",
        "thème de recherche", "research area",
        "research group", "groupe thématique",
    ]):
        return {"intent": "clusters"}

    # ══════════════════════════════════════════════════════════════════════
    # 6. STATISTIQUES GÉNÉRALES
    # ══════════════════════════════════════════════════════════════════════
    if any(k in qn for k in [
        "statistique général", "general statistique",
        "overview", "résumé général", "bilan général",
        "summary", "combien", "total", "nombre de",
        "plateforme", "how many", "platform statistique",
        "vue d'ensemble", "tableau de bord",
    ]):
        return {"intent": "general_stats"}

    # ══════════════════════════════════════════════════════════════════════
    # 7. FALLBACK → Recherche sémantique
    # ══════════════════════════════════════════════════════════════════════
    return {"intent": "semantic_search", "query": question}


# ─── RESPONSE BUILDER ─────────────────────────────────────────────────────────

def build_response(intent_data: dict, question: str) -> dict:
    intent = intent_data.get("intent")

    if intent == "help":
        return {
            "answer": "Je peux répondre aux questions suivantes :",
            "data": {
                "📄 Publications": [
                    "Publications les plus citées ?",
                    "Publications récentes ?",
                    "Publications en 2021 ?",
                    "Publications dans VertigO ?",
                    "Publications sur 'urbanisme' ?",
                ],
                "🔬 Chercheurs": [
                    "Top chercheurs par h-index ?",
                    "Publications de Madjid Chachour ?",
                    "Statistiques de Madjid Chachour ?",
                    "Co-auteurs de Madjid Chachour ?",
                ],
                "🔗 Citations": [
                    "Statistiques des citations ?",
                    "Qui cite 'La verticalisation...' ?",
                ],
                "📰 Journaux": [
                    "Top journaux ?",
                    "Journal VertigO ?",
                ],
                "🏷️ Keywords": [
                    "Top mots-clés ?",
                    "Publications sur humanities ?",
                ],
                "📊 Général": [
                    "Statistiques générales ?",
                    "Groupes thématiques ?",
                ]
            },
            "type": "help", "intent": intent
        }

    # ── Singulier : meilleure publication ────────────────────────────────
    if intent == "best_publication":
        data = best_publication()
        if not data:
            return {"answer": "Aucune publication trouvée.",
                    "data": None, "type": "empty", "intent": intent}
        return {
            "answer": f"La publication la plus citée est : '{data['title'][:80]}' "
                      f"({data['citations']} citations) :",
            "data": data, "type": "publication_single", "intent": intent
        }

    if intent == "highest_cited":
        data = highest_cited_publications()
        return {
            "answer": f"Voici les {len(data)} publications les plus citées :",
            "data": data, "type": "publication_list", "intent": intent
        }

    if intent == "recent_publications":
        data = recent_publications()
        return {
            "answer": "Voici les publications les plus récentes :",
            "data": data, "type": "publication_list", "intent": intent
        }

    if intent == "publications_by_year":
        year = intent_data.get("year")
        data = publications_by_year(year)
        if not data:
            return {"answer": f"Aucune publication trouvée pour l'année {year}.",
                    "data": [], "type": "empty", "intent": intent}
        return {
            "answer": f"Publications de {year} ({len(data)} trouvées) :",
            "data": data, "type": "publication_list", "intent": intent
        }

    if intent == "publications_by_journal":
        jname = intent_data.get("journal", "")
        data  = publications_by_journal(jname)
        if not data:
            return {"answer": f"Aucune publication trouvée pour le journal '{jname}'.",
                    "data": [], "type": "empty", "intent": intent}
        return {
            "answer": f"Publications dans '{jname}' ({len(data)} trouvées) :",
            "data": data, "type": "publication_list", "intent": intent
        }

    if intent == "publications_by_keyword":
        kw   = intent_data.get("keyword", "")
        data = publications_by_keyword(kw)
        if not data:
            return {"answer": f"Aucune publication trouvée pour '{kw}'.",
                    "data": [], "type": "empty", "intent": intent}
        return {
            "answer": f"Publications sur '{kw}' ({len(data)} trouvées) :",
            "data": data, "type": "publication_list", "intent": intent
        }

    # ── Singulier : meilleur chercheur ──────────────────────────────────
    if intent == "best_researcher":
        data = best_researcher()
        if not data:
            return {"answer": "Aucun chercheur trouvé.",
                    "data": None, "type": "empty", "intent": intent}
        return {
            "answer": f"Le meilleur chercheur est {data['name']} "
                      f"avec un h-index de {data['h_index']} :",
            "data": data, "type": "researcher_single", "intent": intent
        }

    if intent == "top_researchers":
        data = top_researchers()
        return {
            "answer": "Voici les meilleurs chercheurs par h-index :",
            "data": data, "type": "researcher_list", "intent": intent
        }

    if intent == "researcher_publications":
        name = intent_data.get("name", "")
        data = researcher_publications(name)
        if not data:
            return {"answer": f"Aucun chercheur trouvé avec le nom '{name}'.",
                    "data": [], "type": "empty", "intent": intent}
        return {
            "answer": f"Publications de {data['researcher']} "
                      f"({len(data['publications'])} trouvées) :",
            "data": data, "type": "researcher_publications", "intent": intent
        }

    if intent == "researcher_stats":
        name = intent_data.get("name", "")
        data = researcher_stats(name)
        if not data:
            return {"answer": f"Aucun chercheur trouvé avec le nom '{name}'.",
                    "data": [], "type": "empty", "intent": intent}
        return {
            "answer": f"Statistiques de {data['name']} :",
            "data": data, "type": "researcher_stats", "intent": intent
        }

    if intent == "coauthors":
        name = intent_data.get("name", "")
        data = coauthors_of_researcher(name)
        if not data:
            return {"answer": f"Aucun chercheur trouvé avec le nom '{name}'.",
                    "data": [], "type": "empty", "intent": intent}
        return {
            "answer": f"Co-auteurs de {data['researcher']} :",
            "data": data, "type": "coauthor_list", "intent": intent
        }

    if intent == "citations_of_pub":
        title = intent_data.get("title", "")
        data  = citations_of_publication(title)
        if not data:
            return {"answer": f"Aucune publication trouvée pour '{title}'.",
                    "data": [], "type": "empty", "intent": intent}
        return {
            "answer": f"Citations de '{data['publication'][:60]}' :",
            "data": data, "type": "citation_detail", "intent": intent
        }

    if intent == "citation_stats":
        data = citation_stats()
        return {
            "answer": "Statistiques des citations :",
            "data": data, "type": "citation_stats", "intent": intent
        }

    # ── Singulier : meilleur journal ─────────────────────────────────────
    if intent == "best_journal":
        data = best_journal()
        if not data:
            return {"answer": "Aucun journal trouvé.",
                    "data": None, "type": "empty", "intent": intent}
        return {
            "answer": f"Le meilleur journal est '{data['name']}' "
                      f"avec {data['total_citations']} citations :",
            "data": data, "type": "journal_single", "intent": intent
        }

    if intent == "top_journals":
        data = top_journals()
        return {
            "answer": "Voici les journaux avec le plus de citations :",
            "data": data, "type": "journal_list", "intent": intent
        }

    if intent == "journal_detail":
        name = intent_data.get("name", "")
        data = journal_detail(name)
        if not data:
            return {"answer": f"Aucun journal trouvé pour '{name}'.",
                    "data": [], "type": "empty", "intent": intent}
        return {
            "answer": f"Détails du journal '{data['name']}' :",
            "data": data, "type": "journal_detail", "intent": intent
        }

    # ── Singulier : meilleur keyword ─────────────────────────────────────
    if intent == "best_keyword":
        data = best_keyword()
        if not data:
            return {"answer": "Aucun mot-clé trouvé.",
                    "data": None, "type": "empty", "intent": intent}
        return {
            "answer": f"Le mot-clé le plus fréquent est '{data['keyword']}' "
                      f"({data['publications']} publications) :",
            "data": data, "type": "keyword_single", "intent": intent
        }

    if intent == "top_keywords":
        data = top_keywords()
        return {
            "answer": "Voici les mots-clés les plus fréquents :",
            "data": data, "type": "keyword_list", "intent": intent
        }

    if intent == "clusters":
        data = cluster_publications()
        return {
            "answer": "Voici les groupes thématiques de recherche :",
            "data": data, "type": "clusters", "intent": intent
        }

    if intent == "general_stats":
        data = general_stats()
        return {
            "answer": "Voici les statistiques générales de la plateforme :",
            "data": data, "type": "general_stats", "intent": intent
        }

    # ── Fallback sémantique ───────────────────────────────────────────────
    query = intent_data.get("query", question)
    data  = semantic_search(query)
    if not data:
        data = search_publications(query)
    if not data:
        return {
            "answer": (
                "Je n'ai pas trouvé de résultat pour votre question. "
                "Tapez 'aide' pour voir ce que je peux faire."
            ),
            "data": [], "type": "no_result", "intent": "unknown"
        }
    return {
        "answer": f"Voici les résultats pour '{query}' :",
        "data": data, "type": "search_results", "intent": "semantic_search"
    }


# ─── POINT D'ENTRÉE ───────────────────────────────────────────────────────────

def process_question(question: str, context: dict = None) -> dict:
    if context is None:
        context = {}

    if not question or not question.strip():
        return {
            "answer": "Veuillez poser une question.",
            "data": None, "type": "error", "intent": "empty"
        }

    intent_data = detect_intent(question)
    response    = build_response(intent_data, question)

    response["context"] = {
        "intent":           response.get("intent"),
        "last_question":    question,
        "normalized":       normalize(question),
        "last_intent_data": intent_data,
    }

    return response