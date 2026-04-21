# data_pipeline/views.py
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status


class VerifyOrcidView(APIView):
    """
    POST /api/pipeline/verify-orcid/
    Vérifie l'ORCID saisi par le chercheur sur OpenAlex.
    Ne sauvegarde pas encore.

    body : { "orcid": "0000-0002-1825-0097" }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        orcid = request.data.get("orcid", "").strip()

        # Nettoyer l'URL complète si collée
        if "orcid.org/" in orcid:
            orcid = orcid.split("orcid.org/")[-1].strip()

        if not orcid:
            return Response(
                {"error": "ORCID requis."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Vérifier doublon
        from users.models import Researcher
        existing = Researcher.objects.filter(orcid=orcid)
        try:
            existing = existing.exclude(pk=request.user.researcher_profile.pk)
        except Exception:
            pass

        if existing.exists():
            return Response(
                {"valid": False, "error": "Cet ORCID est déjà associé à un autre compte."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Vérification OpenAlex
        from data_pipeline.openalex_verify import verify_orcid
        result = verify_orcid(orcid)

        if not result["valid"]:
            return Response(
                {"valid": False, "error": result["error"]},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response({
            "valid":   True,
            "message": "ORCID vérifié avec succès sur OpenAlex.",
            "profile": result["profile"],
        })


class SaveOrcidAndSyncView(APIView):
    """
    POST /api/pipeline/save-orcid/
    Sauvegarde l'ORCID et lance la sync automatique des publications.

    body : { "orcid": "0000-0002-1825-0097" }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        orcid = request.data.get("orcid", "").strip()

        if "orcid.org/" in orcid:
            orcid = orcid.split("orcid.org/")[-1].strip()

        if not orcid:
            return Response(
                {"error": "ORCID requis."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Vérifier profil Researcher
        try:
            researcher = request.user.researcher_profile
        except Exception:
            return Response(
                {"error": "Profil chercheur introuvable."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Vérifier doublon
        from users.models import Researcher
        if Researcher.objects.filter(orcid=orcid).exclude(pk=researcher.pk).exists():
            return Response(
                {"error": "Cet ORCID est déjà associé à un autre compte."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Vérification finale OpenAlex
        from data_pipeline.openalex_verify import verify_orcid
        result = verify_orcid(orcid)

        if not result["valid"]:
            return Response(
                {"valid": False, "error": result["error"]},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Sauvegarder ORCID
        researcher.orcid = orcid
        researcher.save(update_fields=["orcid"])

        # Mettre à jour h_index depuis OpenAlex directement
        h_index = result["profile"].get("h_index", 0)
        if h_index:
            researcher.h_index = h_index
            researcher.save(update_fields=["h_index"])

        # Lancer sync publications
        from data_pipeline.openalex_researcher_sync import sync_researcher
        stats = sync_researcher(orcid)

        return Response({
            "message": "ORCID sauvegardé et publications importées avec succès.",
            "orcid":   orcid,
            "profile": result["profile"],
            "stats": {
                "publications_created": stats.get("created", 0),
                "publications_updated": stats.get("updated", 0),
                "h_index":              researcher.h_index,
            },
        })


class SyncPublicationsView(APIView):
    """
    POST /api/pipeline/sync/
    Relance la sync manuellement (si nouvelles publications sur OpenAlex).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            researcher = request.user.researcher_profile
        except Exception:
            return Response(
                {"error": "Profil chercheur introuvable."},
                status=status.HTTP_403_FORBIDDEN
            )

        if not researcher.orcid:
            return Response(
                {"error": "Aucun ORCID associé à votre compte."},
                status=status.HTTP_400_BAD_REQUEST
            )

        from data_pipeline.openalex_researcher_sync import sync_researcher
        stats = sync_researcher(researcher.orcid)

        return Response({
            "message": "Synchronisation terminée.",
            "stats": {
                "publications_created": stats.get("created", 0),
                "publications_updated": stats.get("updated", 0),
                "h_index":              researcher.h_index,
            },
        })