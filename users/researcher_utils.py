# users/researcher_utils.py

from publication.models import Publication
from coAuthor.models import CoAuthor
from citation.models import Citation

def get_researcher_publications_with_details(researcher):
    """
    Récupère toutes les publications d'un chercheur avec détails complets
    
    Retourne pour chaque publication :
    - Rôle du chercheur (first author, corresponding, etc.)
    - Liste des co-auteurs
    - Citations reçues
    - Journal et impact factor
    - Keywords
    """
    publications = researcher.publications.all().select_related(
        'journal', 'institution'
    ).prefetch_related('keywords', 'coauthors')
    
    result = []
    for pub in publications:
        # Trouver le rôle du chercheur dans cette publication
        coauthor = CoAuthor.objects.filter(
            publication=pub,
            author_orcid=researcher.orcid
        ).first()
        
        # Récupérer les co-auteurs (autres que le chercheur)
        other_coauthors = CoAuthor.objects.filter(
            publication=pub
        ).exclude(author_orcid=researcher.orcid)
        
        result.append({
            "publication": {
                "id": pub.id,
                "title": pub.title,
                "abstract": pub.abstract,
                "doi": pub.doi,
                "year": pub.publication_year,
                "citation_count": pub.citation_count,
                "altmetric_score": pub.altmetric_score,
            },
            "researcher_role": {
                "order": coauthor.author_order if coauthor else None,
                "contribution_type": coauthor.contribution_type if coauthor else None,
                "is_first_author": coauthor.author_order == 1 if coauthor else False,
                "is_corresponding": coauthor.contribution_type == 4 if coauthor else False,
            },
            "coauthors": [
                {
                    "name": ca.author_name,
                    "orcid": ca.author_orcid,
                    "order": ca.author_order,
                    "is_registered": ca.is_registered
                }
                for ca in other_coauthors
            ],
            "journal": {
                "name": pub.journal.name if pub.journal else None,
                "impact_factor": pub.journal.impact_factor if pub.journal else None,
                "issn": pub.journal.issn if pub.journal else None,
            },
            "keywords": [kw.label for kw in pub.keywords.all()],
            "citations_received": pub.get_citation_count(),
        })
    
    return result


def get_researcher_collaboration_network(researcher, depth=1):
    """
    Récupère le réseau de collaboration d'un chercheur
    
    depth=1: Co-auteurs directs
    depth=2: Co-auteurs des co-auteurs
    """
    from collections import Counter
    
    # Publications du chercheur
    publications = researcher.publications.all()
    
    # Trouver tous les co-auteurs
    collaborators = {}
    
    for pub in publications:
        coauthors = CoAuthor.objects.filter(
            publication=pub
        ).exclude(author_orcid=researcher.orcid)
        
        for ca in coauthors:
            key = ca.author_orcid or ca.author_name
            if key not in collaborators:
                collaborators[key] = {
                    "name": ca.author_name,
                    "orcid": ca.author_orcid,
                    "is_registered": ca.is_registered,
                    "publications": set(),
                    "total_collaborations": 0
                }
            collaborators[key]["publications"].add(pub.id)
            collaborators[key]["total_collaborations"] += 1
    
    # Convertir sets en listes
    for collab in collaborators.values():
        collab["publications"] = list(collab["publications"])
        collab["total_collaborations"] = len(collab["publications"])
    
    # Trier par nombre de collaborations
    sorted_collabs = sorted(
        collaborators.values(),
        key=lambda x: x["total_collaborations"],
        reverse=True
    )
    
    return {
        "researcher": {
            "name": researcher.user.username,
            "orcid": researcher.orcid,
            "h_index": researcher.h_index
        },
        "total_collaborators": len(sorted_collabs),
        "collaborators": sorted_collabs[:20]  # Top 20
    }