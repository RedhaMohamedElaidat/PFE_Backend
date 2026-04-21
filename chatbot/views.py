"""
views.py — Vue principale du chatbot
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status

from .ai_engine import process_question
from .models import ChatMessage
from .context_manager import get_last_context, update_context


class ChatbotView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):

        # ── Validation ────────────────────────────────────────────────────
        question = (request.data.get("message") or "").strip()

        if not question:
            return Response(
                {"error": "Le champ 'message' est requis et ne peut pas être vide."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(question) > 1000:
            return Response(
                {"error": "Le message est trop long (max 1000 caractères)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── Contexte ──────────────────────────────────────────────────────
        user    = request.user if request.user.is_authenticated else None
        context = get_last_context(user) if user else {}

        # ── Traitement ────────────────────────────────────────────────────
        try:
            result = process_question(question, context)
        except Exception as e:
            return Response(
                {"error": f"Erreur de traitement: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # ── Extraction réponse ────────────────────────────────────────────
        answer      = result.get("answer", "")
        data        = result.get("data")
        resp_type   = result.get("type", "unknown")
        new_context = result.get("context", {})

        final_context = update_context(context, new_context)

        # ── Sauvegarde messages ───────────────────────────────────────────
        if user:
            ChatMessage.objects.create(
                user=user,
                role="user",
                message=question
            )
            ChatMessage.objects.create(
                user=user,
                role="assistant",
                message=str(answer),
                context=final_context
            )

        return Response({
            "question": question,
            "answer":   answer,
            "data":     data,
            "type":     resp_type,
            "context":  final_context,
        }, status=status.HTTP_200_OK)

    def get(self, request):
        """
        Retourne l'historique des messages de l'utilisateur connecté.
        """
        user = request.user
        if not user.is_authenticated:
            return Response(
                {"error": "Authentification requise."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        messages = ChatMessage.objects.filter(
            user=user
        ).order_by("-created_at")[:50]

        return Response({
            "history": [
                {
                    "role":       m.role,
                    "message":    m.message,
                    "created_at": m.created_at,
                }
                for m in reversed(list(messages))
            ]
        })


class ChatHistoryView(APIView):
    """
    Vue pour consulter et effacer l'historique.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        messages = ChatMessage.objects.filter(
            user=request.user
        ).order_by("created_at")

        return Response({
            "count": messages.count(),
            "messages": [
                {
                    "id":         m.id,
                    "role":       m.role,
                    "message":    m.message,
                    "created_at": m.created_at,
                }
                for m in messages
            ]
        })

    def delete(self, request):
        deleted, _ = ChatMessage.objects.filter(user=request.user).delete()
        return Response({
            "message": f"{deleted} messages supprimés."
        })