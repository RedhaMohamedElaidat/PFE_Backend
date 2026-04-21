"""
semantic_search.py — Recherche sémantique avec SentenceTransformer
Lazy loading pour éviter crash au démarrage.
"""
import logging
import warnings
import os

logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
warnings.filterwarnings("ignore")
os.environ["TOKENIZERS_PARALLELISM"] = "false"

_model = None


def get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as e:
            logging.error(f"Erreur chargement modèle: {e}")
            return None
    return _model


def semantic_search(query: str, top_k: int = 5) -> list:
    from publication.models import Publication
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity

    model = get_model()

    pubs = list(
        Publication.objects.select_related('journal')
        .order_by('-citation_count')[:500]  # limiter pour performance
    )

    if not pubs:
        return []

    titles = [p.title for p in pubs]

    # Fallback texte si modèle indisponible
    if model is None:
        query_lower = query.lower()
        results = []
        for p in pubs:
            if any(word in p.title.lower() for word in query_lower.split()):
                results.append({
                    "title":     p.title,
                    "year":      p.publication_year,
                    "citations": p.citation_count,
                    "journal":   p.journal.name if p.journal else "-",
                    "score":     1.0,
                })
        return results[:top_k]

    try:
        embeddings     = model.encode(titles, show_progress_bar=False)
        query_emb      = model.encode([query], show_progress_bar=False)
        similarities   = cosine_similarity(query_emb, embeddings)[0]
        top_indices    = np.argsort(similarities)[-top_k:][::-1]

        results = []
        for idx in top_indices:
            p     = pubs[int(idx)]
            score = float(similarities[idx])
            if score > 0.1:  # seuil minimum de pertinence
                results.append({
                    "title":     p.title,
                    "year":      p.publication_year,
                    "citations": p.citation_count,
                    "journal":   p.journal.name if p.journal else "-",
                    "score":     round(score, 3),
                })
        return results

    except Exception as e:
        logging.error(f"Erreur semantic search: {e}")
        return []