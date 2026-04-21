# bibliometrix/run_r_analysis.py
"""
Lance l'analyse R depuis Django
"""

import subprocess
import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def run_bibliometrix_analysis():
    """
    Lance le script R d'analyse bibliometrique
    """
    r_script = Path(__file__).parent / "R_scripts" / "analyze_big_data.R"
    
    if not r_script.exists():
        raise FileNotFoundError(f"Script R introuvable: {r_script}")
    
    print("\n" + "="*70)
    print("  🚀 LANCEMENT ANALYSE R BIBLIOMETRIX")
    print("="*70 + "\n")
    
    # Lancer R
    result = subprocess.run(
        ['Rscript', str(r_script)],
        capture_output=True,
        text=True,
        timeout=600  # 10 minutes max
    )
    
    print(result.stdout)
    
    if result.stderr:
        print("⚠️  R Warnings/Errors:")
        print(result.stderr)
    
    if result.returncode != 0:
        raise Exception(f"R script failed: {result.stderr}")
    
    print("\n✅ Analyse terminée avec succès")
    
    return True


def load_results():
    """
    Charge les résultats JSON générés par R
    """
    results_dir = Path("bibliometrix_results")
    results_dir.mkdir(exist_ok=True)
    
    all_results = {}
    
    for json_file in results_dir.glob("*.json"):
        with open(json_file, 'r', encoding='utf-8') as f:
            all_results[json_file.stem] = json.load(f)
    
    return all_results


if __name__ == "__main__":
    # Lancer l'analyse
    run_bibliometrix_analysis()
    
    # Charger les résultats
    results = load_results()
    print(f"\n📊 Résultats chargés: {list(results.keys())}")