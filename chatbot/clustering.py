"""
clustering.py — Clustering thématique des publications avec KMeans + TF-IDF
"""
import logging


def cluster_publications(k: int = 5) -> dict:
    from publication.models import Publication

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.cluster import KMeans
    except ImportError:
        logging.error("sklearn non installé")
        return {}

    pubs  = list(Publication.objects.all())
    texts = [p.title for p in pubs if p.title]

    if not texts:
        return {}

    # ✅ Ajuster k si pas assez de publications
    k = min(k, len(texts))
    if k < 2:
        return {
            "cluster_0": [
                {"title": p.title, "year": p.publication_year}
                for p in pubs[:5]
            ]
        }

    try:
        # ✅ Vectorizer local (pas global)
        vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=1000,
            ngram_range=(1, 2)
        )
        X = vectorizer.fit_transform(texts)

        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X)

        # ✅ Extraire les termes représentatifs de chaque cluster
        feature_names = vectorizer.get_feature_names_out()
        cluster_terms = {}
        for i in range(k):
            center     = kmeans.cluster_centers_[i]
            top_terms  = [feature_names[j] for j in center.argsort()[-3:][::-1]]
            cluster_terms[i] = ", ".join(top_terms)

        clusters = {}
        for pub, label in zip(pubs, labels):
            label_int = int(label)
            key       = f"cluster_{label_int}"
            theme     = cluster_terms.get(label_int, f"Thème {label_int}")

            if key not in clusters:
                clusters[key] = {
                    "theme": theme,
                    "publications": []
                }
            clusters[key]["publications"].append({
                "title": pub.title,
                "year":  pub.publication_year,
            })

        return clusters

    except Exception as e:
        logging.error(f"Erreur clustering: {e}")
        return {}