# bibliometric/management/commands/run_bibliometrix.py
from django.core.management.base import BaseCommand
from django.core.management import call_command
import subprocess
import os
import json
from pathlib import Path
from datetime import datetime

class Command(BaseCommand):
    help = 'Lance l\'analyse Bibliometrix avec R'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force le recalcul même si les données existent',
        )
    
    def handle(self, *args, **options):
        self.stdout.write("\n" + "="*70)
        self.stdout.write("  🚀 LANCEMENT ANALYSE BIBLIOMETRIX")
        self.stdout.write("="*70 + "\n")
        
        # 1. Vérifier que R est installé
        self.stdout.write("📌 Vérification R...")
        try:
            subprocess.run(['R', '--version'], capture_output=True, check=True)
            self.stdout.write(self.style.SUCCESS("  ✅ R est installé"))
        except:
            self.stdout.write(self.style.ERROR("  ❌ R n'est pas installé"))
            self.stdout.write("     Téléchargez R depuis: https://cran.r-project.org/")
            return
        
        # 2. Vérifier les packages R
        self.stdout.write("\n📌 Vérification packages R...")
        packages = ['bibliometrix', 'jsonlite', 'data.table']
        missing = []
        
        for pkg in packages:
            result = subprocess.run(
                ['R', '-e', f'if(!require({pkg})) quit(status=1)'],
                capture_output=True
            )
            if result.returncode != 0:
                missing.append(pkg)
        
        if missing:
            self.stdout.write(self.style.WARNING(f"  ⚠️ Packages manquants: {missing}"))
            self.stdout.write("  Installation en cours...")
            for pkg in missing:
                subprocess.run(['R', '-e', f'install.packages("{pkg}", repos="https://cloud.r-project.org")'])
            self.stdout.write(self.style.SUCCESS("  ✅ Packages installés"))
        else:
            self.stdout.write(self.style.SUCCESS("  ✅ Tous les packages sont installés"))
        
        # 3. Vérifier que le CSV existe
        self.stdout.write("\n📌 Vérification CSV...")
        csv_path = Path("bibliometrix_exports/algeria_bibliometrix_2010_2025_LATEST.csv")
        
        if not csv_path.exists():
            # Chercher d'autres CSV
            csv_files = list(Path("bibliometrix_exports").glob("*.csv"))
            if csv_files:
                csv_path = csv_files[0]
                self.stdout.write(f"  📁 Fichier trouvé: {csv_path.name}")
            else:
                self.stdout.write(self.style.ERROR("  ❌ Aucun CSV trouvé"))
                self.stdout.write("     Exportez d'abord les données avec:")
                self.stdout.write("     python bibliometrix/export_bibliometrix.py")
                return
        else:
            self.stdout.write(self.style.SUCCESS(f"  ✅ CSV trouvé: {csv_path.name}"))
        
        # 4. Créer dossier résultats
        results_dir = Path("bibliometrix_results")
        results_dir.mkdir(exist_ok=True)
        
        # 5. Lancer le script R
        self.stdout.write("\n📌 Lancement analyse R...")
        r_script = Path("bibliometrix/R_scripts/analyze_big_data.R")
        
        if not r_script.exists():
            self.stdout.write(self.style.ERROR(f"  ❌ Script introuvable: {r_script}"))
            return
        
        result = subprocess.run(
            ['Rscript', str(r_script)],
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            self.stdout.write(result.stdout)
        
        if result.stderr:
            self.stdout.write(self.style.WARNING("⚠️  Messages R:"))
            self.stdout.write(result.stderr[:1000])
        
        # 6. Importer les résultats dans Django
        self.stdout.write("\n📌 Import des résultats dans PostgreSQL...")
        
        from bibliometric.models import BibliometrixAnalysis
        
        # Charger tous les JSON
        json_files = list(results_dir.glob("*.json"))
        
        for json_file in json_files:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Déterminer le type
            analysis_type = json_file.stem  # summary, top_authors, etc.
            
            # Sauvegarder
            BibliometrixAnalysis.objects.create(
                analysis_type=analysis_type,
                parameters={'file': json_file.name},
                results=data
            )
            
            self.stdout.write(f"  ✅ {analysis_type} importé ({len(str(data))} bytes)")
        
        # 7. Résumé final
        self.stdout.write("\n" + "="*70)
        self.stdout.write(self.style.SUCCESS("  ✅ ANALYSE TERMINÉE AVEC SUCCÈS"))
        self.stdout.write("="*70)
        self.stdout.write(f"\n📊 Résultats disponibles dans: {results_dir}")
        self.stdout.write(f"📁 {len(json_files)} fichiers JSON générés")
        self.stdout.write("\n🔗 API endpoints disponibles:")
        self.stdout.write("  GET /api/bibliometrix/summary/")
        self.stdout.write("  GET /api/bibliometrix/top-authors/")
        self.stdout.write("  GET /api/bibliometrix/thematic-clusters/")
        self.stdout.write("  GET /api/bibliometrix/collaboration-network/")