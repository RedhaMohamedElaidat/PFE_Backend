"""
export_to_bibliometrix.py

Exporte les données PostgreSQL → CSV format Bibliometrix (R)

Format Bibliometrix standard :
AU    = Authors
TI    = Title
PY    = Publication Year
SO    = Source/Journal
TC    = Times Cited
DE    = Keywords (author)
ID    = Keywords (indexed)
AB    = Abstract
C1    = Affiliation
RP    = Reprint author
"""

import csv
import os
from datetime import datetime, date
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


def export_algeria_to_bibliometrix(
    output_dir: str = "/mnt/user-data/outputs",
    filename: str = "algeria_bibliometrix.csv",
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    include_abstracts: bool = True,
    last_n_years: int = 15  # ✅ NOUVEAU PARAMÈTRE : 15 dernières années par défaut
) -> Dict:
    """
    ✅ Exporte les publications Algérie en format Bibliometrix
    
    Paramètres :
    - output_dir : Dossier de destination
    - filename : Nom du fichier CSV
    - year_min, year_max : Filtrer par année (si fournis, ignore last_n_years)
    - include_abstracts : Inclure les abstracts (plus gros fichier)
    - last_n_years : Nombre d'années à exporter (défaut: 15, calcule automatiquement)
    
    Retourne : Statistiques d'export
    """
    
    print(f"\n{'='*70}")
    print(f"  📊 EXPORT VERS BIBLIOMETRIX")
    print(f"{'='*70}\n")
    
    from publication.models import Publication
    from coAuthor.models import CoAuthor
    
    # ────────────────── ÉTAPE 1 : Déterminer la plage d'années ──────────────────
    current_year = date.today().year
    
    if year_min is None and year_max is None:
        # ✅ Mode automatique : dernière N années
        year_max = current_year
        year_min = current_year - last_n_years + 1
        print(f"  📅 Mode automatique : {last_n_years} dernières années")
        print(f"     📅 Plage : {year_min} → {year_max}")
    elif year_min is not None and year_max is None:
        # Seulement year_min fourni
        year_max = current_year
        print(f"  📅 Plage personnalisée : {year_min} → {year_max}")
    elif year_min is None and year_max is not None:
        # Seulement year_max fourni
        year_min = 2010  # fallback
        print(f"  📅 Plage personnalisée : {year_min} → {year_max}")
    else:
        print(f"  📅 Plage personnalisée : {year_min} → {year_max}")
    
    # ────────────────── ÉTAPE 2 : Récupérer les publications ──────────────────
    print(f"\n  📄 Récupération des publications...")
    
    queryset = Publication.objects.all().select_related(
        'journal', 'institution'
    ).prefetch_related(
        'keywords', 'coauthors'
    )
    
    # Filtrer par année
    if year_min:
        queryset = queryset.filter(publication_year__gte=year_min)
    if year_max:
        queryset = queryset.filter(publication_year__lte=year_max)
    
    publications = list(queryset)
    print(f"     ✅ {len(publications)} publications trouvées")
    
    if not publications:
        print(f"  ❌ Aucune publication à exporter")
        return {"status": "failed", "count": 0}
    
    # ────────────────── ÉTAPE 3 : Créer le répertoire ──────────────────
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    
    # ────────────────── ÉTAPE 4 : Écrire le CSV ──────────────────
    print(f"  📝 Écriture du fichier CSV...")
    
    start_time = datetime.now()
    
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            # Champs Bibliometrix standard
            fieldnames = [
                'AU',       # Authors (comma-separated)
                'TI',       # Title
                'PY',       # Publication Year
                'SO',       # Source (Journal)
                'TC',       # Times Cited (citation count)
                'DE',       # Author keywords
                'ID',       # Keywords Plus (indexed)
                'AB',       # Abstract
                'C1',       # Affiliation
                'RP',       # Reprint author (first author)
                'DI',       # DOI
                'PU',       # Publisher
                'PI',       # Impact Factor
                'AF',       # All Authors (with affiliation)
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            # ────────────────── BOUCLE : Exporter chaque publication ──────────────────
            for pub in publications:
                
                # 🟢 AU : Authors (comma-separated, format: Lastname, Initials)
                authors = _get_authors_list(pub)
                au_field = ";".join(authors) if authors else "Unknown"
                
                # 🟢 TI : Title
                ti_field = pub.title or ""
                
                # 🟢 PY : Publication Year
                py_field = str(pub.publication_year) if pub.publication_year else ""
                
                # 🟢 SO : Source (Journal name)
                so_field = pub.journal.name if pub.journal else "Unknown Journal"
                
                # 🟢 TC : Times Cited (citation count)
                tc_field = str(pub.citation_count or 0)
                
                # 🟢 DE : Keywords (author - from concepts)
                keywords = list(pub.keywords.values_list('label', flat=True))
                de_field = ";".join(keywords) if keywords else ""
                
                # 🟢 ID : Keywords Plus (same as DE for OpenAlex)
                id_field = de_field
                
                # 🟢 AB : Abstract
                ab_field = pub.abstract if include_abstracts and pub.abstract else ""
                
                # 🟢 C1 : Affiliation (institution name)
                c1_field = pub.institution.name if pub.institution else ""
                
                # 🟢 RP : Reprint author (first author)
                rp_field = authors[0] if authors else "Unknown"
                
                # 🟢 DI : DOI
                di_field = pub.doi if pub.doi else ""
                
                # 🟢 PU : Publisher (journal publisher, si disponible)
                pu_field = pub.journal.publisher if pub.journal and hasattr(pub.journal, 'publisher') else ""
                
                # 🟢 PI : Impact Factor (journal IF)
                pi_field = str(pub.journal.impact_factor) if pub.journal and pub.journal.impact_factor else ""
                
                # 🟢 AF : All Authors with affiliations
                af_field = _get_authors_with_affiliations(pub)
                
                # Écrire la ligne
                writer.writerow({
                    'AU': au_field,
                    'TI': ti_field,
                    'PY': py_field,
                    'SO': so_field,
                    'TC': tc_field,
                    'DE': de_field,
                    'ID': id_field,
                    'AB': ab_field,
                    'C1': c1_field,
                    'RP': rp_field,
                    'DI': di_field,
                    'PU': pu_field,
                    'PI': pi_field,
                    'AF': af_field,
                })
        
        elapsed = (datetime.now() - start_time).total_seconds()
        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        
        print(f"     ✅ Fichier créé : {filepath}")
        print(f"     📊 Publications exportées: {len(publications)}")
        print(f"     📈 Taille du fichier: {file_size_mb:.2f} MB")
        print(f"     ⏱️  Temps d'export: {elapsed:.1f}s")
        
        print(f"\n{'='*70}")
        print(f"  ✅ EXPORT RÉUSSI")
        print(f"  📂 Fichier: {filepath}")
        print(f"  📊 Prêt pour Bibliometrix (R)!")
        print(f"{'='*70}\n")
        
        return {
            "status": "success",
            "filepath": filepath,
            "count": len(publications),
            "file_size_mb": file_size_mb,
            "elapsed_seconds": elapsed,
            "year_range": f"{year_min}-{year_max}",
        }
        
    except Exception as e:
        logger.error(f"Erreur lors de l'export: {e}")
        print(f"  ❌ Erreur: {e}")
        return {"status": "failed", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# 🟡 UTILITAIRES
# ─────────────────────────────────────────────────────────────────────────────

def _get_authors_list(publication) -> List[str]:
    """
    ✅ Récupère la liste des auteurs au format Bibliometrix
    
    Format: "Lastname, Initials;Lastname2, Initials2;..."
    Exemple: "Smith, J;Johnson, MA;Williams, RK"
    """
    from coAuthor.models import CoAuthor
    
    coauthors = CoAuthor.objects.filter(
        publication=publication
    ).order_by('author_order')
    
    authors = []
    for ca in coauthors:
        # Utiliser le nom complet si disponible
        name = ca.author_name or "Unknown"
        
        # Convertir en format "Lastname, Initials"
        parts = name.split()
        
        if len(parts) >= 2:
            # Format: Firstname Lastname → Lastname, F
            lastname = parts[-1]
            initials = "".join([p[0].upper() for p in parts[:-1]])
            formatted = f"{lastname},{initials}"
        else:
            # Nom unique
            formatted = name
        
        authors.append(formatted)
    
    return authors


def _get_authors_with_affiliations(publication) -> str:
    """
    ✅ Format: "Author1, Affiliation;Author2, Affiliation;..."
    """
    from coAuthor.models import CoAuthor
    
    coauthors = CoAuthor.objects.filter(
        publication=publication
    ).order_by('author_order')
    
    authors_aff = []
    for ca in coauthors:
        name = ca.author_name or "Unknown"
        aff = ca.affiliation_at_time or ""
        
        if aff:
            authors_aff.append(f"{name},{aff}")
        else:
            authors_aff.append(name)
    
    return ";".join(authors_aff)


# ─────────────────────────────────────────────────────────────────────────────
# 📊 FONCTION BATCH - Exporter dynamiquement les N dernières années
# ─────────────────────────────────────────────────────────────────────────────

def export_algeria_last_n_years(
    output_dir: str = "/mnt/user-data/outputs",
    n_years: int = 15,
    include_abstracts: bool = True
) -> Dict:
    """
    ✅ Exporte les N dernières années (calcul automatique)
    
    Utile pour les analyses temporelles récentes
    """
    current_year = date.today().year
    start_year = current_year - n_years + 1
    
    print(f"\n{'='*70}")
    print(f"  📊 EXPORT DES {n_years} DERNIÈRES ANNÉES ({start_year}-{current_year})")
    print(f"{'='*70}\n")
    
    return export_algeria_to_bibliometrix(
        output_dir=output_dir,
        filename=f"algeria_last_{n_years}_years_bibliometrix.csv",
        year_min=start_year,
        year_max=current_year,
        include_abstracts=include_abstracts
    )


# ─────────────────────────────────────────────────────────────────────────────
# 🎯 POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    import django
    
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Backend.settings')
    django.setup()
    
    # ✅ Option 1 : Exporter les 15 dernières années (automatique)
    result = export_algeria_last_n_years(
        output_dir="C:\\Users\\ridae\\PFE\\Backend\\outputs",
        n_years=15,
        include_abstracts=True
    )
    
    # ✅ Option 2 : Exporter avec plage personnalisée
    # result = export_algeria_to_bibliometrix(
    #     output_dir="C:\\Users\\ridae\\PFE\\Backend\\outputs",
    #     filename="algeria_bibliometrix.csv",
    #     year_min=2020,  # Surcharge manuelle
    #     year_max=2025,
    #     include_abstracts=True
    # )
    
    print(f"\nRésultat: {result}")