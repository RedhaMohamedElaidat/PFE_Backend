
import requests
import re

BASE_URL = "https://api.openalex.org"
HEADERS  = {"User-Agent": "mailto:ridaelaidate7@gmail.com"}  # ← remplace par ton email


def validate_orcid_format(orcid: str):
    """
    Valide le format ORCID.
    Retourne un message d'erreur ou None si valide.
    """
    if not orcid:
        return "L'ORCID ne peut pas être vide."

    orcid = orcid.strip()

    if "orcid.org/" in orcid:
        orcid = orcid.split("orcid.org/")[-1].strip()

    pattern = r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$'
    if not re.match(pattern, orcid):
        return (
            f"Format ORCID invalide : '{orcid}'. "
            "Format attendu : XXXX-XXXX-XXXX-XXXX "
            "(ex: 0000-0002-1825-0097)"
        )
    return None


def verify_orcid(orcid: str) -> dict:
    """
    Vérifie l'ORCID sur OpenAlex.
    Retourne le profil si trouvé, sinon une erreur.
    """
    # Nettoyer
    orcid = orcid.strip()
    if "orcid.org/" in orcid:
        orcid = orcid.split("orcid.org/")[-1].strip()

    # Valider le format
    format_error = validate_orcid_format(orcid)
    if format_error:
        return {"valid": False, "error": format_error}

    # Vérifier sur OpenAlex
    try:
        resp = requests.get(
            f"{BASE_URL}/authors/orcid:{orcid}",
            headers=HEADERS,
            timeout=10
        )

        if resp.status_code == 404:
            return {
                "valid": False,
                "error": (
                    f"ORCID '{orcid}' introuvable sur OpenAlex. "
                    "Vérifiez votre ORCID sur https://orcid.org"
                )
            }

        resp.raise_for_status()
        data    = resp.json()
        profile = extract_profile(data)
        return {"valid": True, "profile": profile}

    except requests.exceptions.ConnectionError:
        return {
            "valid": False,
            "error": "Impossible de contacter OpenAlex. Vérifiez votre connexion."
        }
    except requests.exceptions.Timeout:
        return {
            "valid": False,
            "error": "OpenAlex ne répond pas. Réessayez dans quelques instants."
        }
    except Exception as e:
        return {"valid": False, "error": f"Erreur : {str(e)}"}


def extract_profile(data: dict) -> dict:
    """Extrait les infos utiles du profil OpenAlex."""
    institutions = data.get("last_known_institutions") or []
    inst_name    = institutions[0].get("display_name", "") if institutions else ""
    orcid_raw    = data.get("orcid") or ""
    orcid        = orcid_raw.replace("https://orcid.org/", "").strip()

    return {
        "openalex_id":  data.get("id", ""),
        "display_name": data.get("display_name", ""),
        "orcid":        orcid,
        "works_count":  data.get("works_count", 0),
        "citations":    data.get("cited_by_count", 0),
        "h_index":      (data.get("summary_stats") or {}).get("h_index", 0),
        "institution":  inst_name,
    }