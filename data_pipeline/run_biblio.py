import subprocess
import json
import os

R_SCRIPT_PATH = "data_pipeline/biblio_analysis.R"
OUTPUT_JSON = "C:/Users/ridae/PFE/Backend/outputs/results.json"

def run_bibliometrix():
    try:
        # 🔥 Lancer script R
        subprocess.run(
            ["Rscript", R_SCRIPT_PATH],
            check=True,
            capture_output=True,
            text=True
        )

        print("✅ Analyse R terminée")

        # 📥 Lire résultats JSON
        if os.path.exists(OUTPUT_JSON):
            with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)

            print("✅ Résultats chargés")
            return data
        else:
            print("❌ JSON non trouvé")
            return None

    except subprocess.CalledProcessError as e:
        print("❌ Erreur R:", e.stderr)
        return None


if __name__ == "__main__":
    result = run_bibliometrix()
    print(result)