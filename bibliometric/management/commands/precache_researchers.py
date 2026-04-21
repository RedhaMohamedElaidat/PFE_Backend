# bibliometric/management/commands/run_bibliometrix.py

from django.core.management.base import BaseCommand
from bibliometrix.run_r_analysis import run_bibliometrix_analysis, load_results
from bibliometrix.models import BibliometrixAnalysis
import json

class Command(BaseCommand):
    help = 'Lance l\'analyse Bibliometrix complète avec R'
    
    def handle(self, *args, **options):
        self.stdout.write("🚀 Lancement analyse Bibliometrix...")
        
        try:
            # Lancer R
            run_bibliometrix_analysis()
            
            # Charger résultats
            results = load_results()
            
            # Sauvegarder dans PostgreSQL
            for analysis_name, data in results.items():
                BibliometrixAnalysis.objects.create(
                    analysis_type=analysis_name,
                    parameters={},
                    results=data
                )
                self.stdout.write(f"  ✅ {analysis_name} sauvegardé")
            
            self.stdout.write(self.style.SUCCESS("\n✅ Analyse terminée avec succès!"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Erreur: {e}"))