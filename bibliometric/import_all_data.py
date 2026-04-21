#!/usr/bin/env python
# import_all_data.py - À placer dans le dossier backend (racine du projet)

import json
import os
import sys
from datetime import datetime

# Configuration Django - Correction pour Windows
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django
django.setup()

from django.db import connection
from bibliometric.models import BibliometrixAnalysis, ResearcherBibliometricCache, BibliometrixAnalysisHistory
from users.models import Researcher
from django.contrib.auth import get_user_model

User = get_user_model()

# Couleurs pour terminal Windows
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RED = '\033[91m'
    NC = '\033[0m'

def print_color(text, color=Colors.NC):
    print(f"{color}{text}{Colors.NC}")

def main():
    print_color("\n" + "="*70, Colors.BLUE)
    print_color("  📊 IMPORTATION DES DONNÉES BIBLIOMETRIQUES", Colors.BLUE)
    print_color("="*70 + "\n", Colors.BLUE)
    
    RESULTS_DIR = "bibliometrix_results"
    
    # Vérifier si le dossier existe
    if not os.path.exists(RESULTS_DIR):
        print_color(f"❌ Dossier {RESULTS_DIR} non trouvé!", Colors.RED)
        print_color("Assurez-vous d'avoir exécuté le script R d'abord", Colors.YELLOW)
        return
    
    # ========================================================================
    # 1. VIDER LES TABLES
    # ========================================================================
    print_color("🗑️  Vidage des tables existantes...\n", Colors.YELLOW)
    
    deleted_analyses, _ = BibliometrixAnalysis.objects.all().delete()
    print(f"  ✓ {deleted_analyses} analyses supprimées")
    
    deleted_cache, _ = ResearcherBibliometricCache.objects.all().delete()
    print(f"  ✓ {deleted_cache} caches supprimés")
    
    deleted_history, _ = BibliometrixAnalysisHistory.objects.all().delete()
    print(f"  ✓ {deleted_history} historiques supprimés")
    
    # Réinitialiser les séquences SQLite
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='bibliometrix_analyses'")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='bibliometric_cache'")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='bibliometric_history'")
            print("  ✓ Séquences d'ID réinitialisées")
    except:
        pass
    
    print_color("\n✅ Tables vidées avec succès\n", Colors.GREEN)
    
    # ========================================================================
    # 2. IMPORTER LES ANALYSES
    # ========================================================================
    print_color("📥 Importation des nouvelles analyses...\n", Colors.YELLOW)
    
    files_mapping = {
        "summary.json": "summary",
        "top_100_authors.json": "top_authors",
        "thematic_clusters.json": "thematic_clusters",
        "collaboration_network.json": "collaboration_network",
    }
    
    for filename, analysis_type in files_mapping.items():
        filepath = os.path.join(RESULTS_DIR, filename)
        
        if not os.path.exists(filepath):
            print(f"    ⚠️  Fichier non trouvé: {filename}")
            continue
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            analysis = BibliometrixAnalysis.objects.create(
                analysis_type=analysis_type,
                parameters={
                    "source_file": filename,
                    "import_date": datetime.now().isoformat(),
                    "total_publications": data.get("total_publications", len(data) if isinstance(data, list) else 0)
                },
                results=data
            )
            
            size_kb = len(json.dumps(data)) / 1024
            print(f"    ✓ {analysis_type}: {size_kb:.1f} KB")
            
        except Exception as e:
            print(f"    ❌ Erreur pour {filename}: {str(e)[:100]}")
    
    print_color("\n✅ Analyses importées\n", Colors.GREEN)
    
    # ========================================================================
    # 3. IMPORTER LES DONNÉES COMPLÈTES
    # ========================================================================
    print_color("📦 Importation des données complètes...\n", Colors.YELLOW)
    
    complete_files = {
        "all_authors.json": "all_authors",
        "all_keywords.json": "all_keywords",
        "all_collaboration_edges.json": "collaboration_edges",
        "collaboration_network_complete.json": "collaboration_network_complete",
        "all_author_publications.json": "author_publications",
    }
    
    for filename, analysis_type in complete_files.items():
        filepath = os.path.join(RESULTS_DIR, filename)
        
        if not os.path.exists(filepath):
            print(f"    ⚠️  Fichier non trouvé: {filename}")
            continue
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not BibliometrixAnalysis.objects.filter(analysis_type=analysis_type).exists():
                analysis = BibliometrixAnalysis.objects.create(
                    analysis_type=analysis_type,
                    parameters={"source_file": filename, "is_complete_dataset": True},
                    results=data
                )
                
                size_kb = len(json.dumps(data)) / 1024
                print(f"    ✓ {analysis_type}: {size_kb:.1f} KB")
            else:
                print(f"    ⏭️  {analysis_type} existe déjà")
            
        except Exception as e:
            print(f"    ❌ Erreur pour {filename}: {str(e)[:100]}")
    
    print_color("\n✅ Données complètes importées\n", Colors.GREEN)
    
    # ========================================================================
    # 4. METTRE À JOUR LE CACHE
    # ========================================================================
    print_color("🔄 Mise à jour du cache des chercheurs...\n", Colors.YELLOW)
    
    try:
        all_authors_path = os.path.join(RESULTS_DIR, "all_authors.json")
        author_pubs_path = os.path.join(RESULTS_DIR, "all_author_publications.json")
        collab_path = os.path.join(RESULTS_DIR, "collaboration_network_complete.json")
        
        with open(all_authors_path, 'r', encoding='utf-8') as f:
            all_authors = json.load(f)
        
        with open(author_pubs_path, 'r', encoding='utf-8') as f:
            author_publications = json.load(f)
        
        with open(collab_path, 'r', encoding='utf-8') as f:
            collaboration_data = json.load(f)
        
    except FileNotFoundError as e:
        print(f"  ⚠️  Fichier non trouvé: {e}")
        all_authors = []
        author_publications = {}
        collaboration_data = {}
    
    updated_count = 0
    created_count = 0
    
    for author_data in all_authors[:100]:  # Top 100
        author_name = author_data.get("name", "")
        if not author_name:
            continue
        
        # Recherche approximative du chercheur
        name_parts = author_name.split()
        researchers = Researcher.objects.none()
        
        if name_parts:
            first_name = name_parts[0]
            last_name = name_parts[-1] if len(name_parts) > 1 else ""
            
            if last_name:
                researchers = Researcher.objects.filter(
                    user__first_name__icontains=first_name
                ) | Researcher.objects.filter(
                    user__last_name__icontains=last_name
                )
            else:
                researchers = Researcher.objects.filter(
                    user__first_name__icontains=first_name
                ) | Researcher.objects.filter(
                    user__last_name__icontains=first_name
                )
        
        if not researchers.exists():
            continue
        
        researcher = researchers.first()
        pubs_data = author_publications.get(author_name, {})
        collab = collaboration_data.get(author_name, {})
        
        total_papers = author_data.get("publications", 0)
        total_citations = sum(p.get("citations", 0) for p in pubs_data.get("all_publications", []))
        avg_citations = total_citations / total_papers if total_papers > 0 else 0
        
        years = [p.get("year", 0) for p in pubs_data.get("all_publications", []) if p.get("year")]
        first_year = min(years) if years else None
        last_year = max(years) if years else None
        years_active = len(set(years)) if years else 0
        
        yearly_output = {}
        for pub in pubs_data.get("all_publications", []):
            year = pub.get("year")
            if year:
                yearly_output[year] = yearly_output.get(year, 0) + 1
        
        cache, created = ResearcherBibliometricCache.objects.update_or_create(
            researcher=researcher,
            defaults={
                'h_index': 0,
                'g_index': 0,
                'm_index': 0.0,
                'total_papers': total_papers,
                'total_citations': total_citations,
                'avg_citations': round(avg_citations, 2),
                'yearly_output': yearly_output,
                'yearly_citations': {},
                'top_keywords': [],
                'top_journals': [],
                'collaboration_network': collab,
                'first_publication_year': first_year,
                'last_publication_year': last_year,
                'years_active': years_active,
            }
        )
        
        if created:
            created_count += 1
        else:
            updated_count += 1
    
    print(f"  ✓ Cache créé: {created_count} chercheurs")
    print(f"  ✓ Cache mis à jour: {updated_count} chercheurs")
    print_color("\n✅ Cache des chercheurs mis à jour\n", Colors.GREEN)
    
    # ========================================================================
    # 5. STATISTIQUES FINALES
    # ========================================================================
    print_color("="*70, Colors.BLUE)
    print_color("✅ IMPORTATION TERMINÉE AVEC SUCCÈS", Colors.GREEN)
    print_color("="*70 + "\n", Colors.BLUE)
    
    analyses_count = BibliometrixAnalysis.objects.count()
    cache_count = ResearcherBibliometricCache.objects.count()
    
    print("📊 STATISTIQUES FINALES:")
    print(f"  • Analyses bibliométriques: {analyses_count}")
    print(f"  • Caches chercheurs: {cache_count}")
    print()
    
    if analyses_count > 0:
        print("📁 Types d'analyses importées:")
        for analysis in BibliometrixAnalysis.objects.all()[:10]:
            size_kb = len(str(analysis.results)) / 1024
            print(f"    - {analysis.analysis_type}: {size_kb:.1f} KB")
    
    print_color("\n✨ Vous pouvez maintenant accéder aux données dans l'admin Django", Colors.GREEN)
    print("   URL: http://localhost:8000/admin/bibliometric/\n")

if __name__ == "__main__":
    main()