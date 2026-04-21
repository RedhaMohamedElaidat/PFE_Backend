# users/views.py
from time import timezone

from rest_framework import generics, viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView  # ← Ajoutez ceci
from django_filters.rest_framework import DjangoFilterBackend # type: ignore
from django.db.models import Q  # ← Ajoutez ceci
from django.contrib.auth import get_user_model  # ← Ajoutez ceci
from users.models import User, Researcher, Admin, LabManager, TeamLeader
from rest_framework import filters
from users.serializers import (
    UserSerializer, RegisterSerializer, ChangePasswordSerializer,
    ResearcherSerializer, ResearcherUpdateSerializer,
    AdminSerializer, LabManagerSerializer, TeamLeaderSerializer
)
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from users.models import Researcher
from django.db.models import Q
from django.db import models
# IMPORTATION DU PIPELINE OPENALEX
from data_pipeline.openalex_verify import verify_orcid
from data_pipeline.openalex_researcher_sync import sync_researcher
import logging
from users.permissions import IsCustomAdmin, IsSuperAdmin

logger = logging.getLogger(__name__)

# Obtenir le modèle User
User = get_user_model()


# ─── Auth ─────────────────────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        print("📥 Données reçues:", request.data)
        serializer = self.get_serializer(data=request.data)
        print("📝 Données serializer:", serializer.initial_data)  # ← AJOUTER
    
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            print("❌ Erreur:", serializer.errors)  # ← AJOUTER
            raise
        serializer.is_valid(raise_exception=True)
        
        username = request.data.get('username')
        email = request.data.get('email')
        
        # Vérifier si l'utilisateur existe déjà
        existing_user = None
        try:
            existing_user = User.objects.get(Q(username=username) | Q(email=email))
        except User.DoesNotExist:
            pass
        
        # Si l'utilisateur existe déjà
        if existing_user:
            # Si c'est un utilisateur externe (créé par OpenAlex)
            if existing_user.is_external:
                return Response({
                    'exists': True,
                    'is_external': True,
                    'message': 'Un compte existe déjà avec ces informations. '
                               'Veuillez réinitialiser votre mot de passe pour activer votre compte.',
                    'username': existing_user.username,
                    'email': existing_user.email,
                    'action': 'reset_password'
                }, status=status.HTTP_409_CONFLICT)
            
            # Si c'est un utilisateur normal mais désactivé
            elif not existing_user.is_active:
                return Response({
                    'exists': True,
                    'is_active': False,
                    'message': 'Votre compte est désactivé. Veuillez contacter un administrateur.',
                    'action': 'contact_admin'
                }, status=status.HTTP_409_CONFLICT)
            
            # Si l'utilisateur existe déjà et est actif
            else:
                return Response({
                    'exists': True,
                    'is_active': True,
                    'message': 'Un compte existe déjà avec ces informations. '
                               'Veuillez vous connecter ou réinitialiser votre mot de passe.',
                    'action': 'login_or_reset'
                }, status=status.HTTP_409_CONFLICT)
        
        # Si l'utilisateur n'existe pas, créer un nouveau compte
        user = serializer.save()
        
        return Response({
            'success': True,
            'message': 'Compte créé avec succès. Vous pouvez maintenant vous connecter.',
            'user': {
                'id': user.user_id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name
            }
        }, status=status.HTTP_201_CREATED)


class ChangePasswordView(generics.UpdateAPIView):
    serializer_class   = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save()
        return Response({'detail': 'Mot de passe mis à jour avec succès.'})
    
    # Add this method to accept POST requests
    def post(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

class PasswordResetRequestView(APIView):
    """
    Demande de réinitialisation de mot de passe
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'error': 'Email requis'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'Aucun compte associé à cet email'}, 
                          status=status.HTTP_404_NOT_FOUND)
        
        # Générer un token de réinitialisation
        import secrets
        from django.utils import timezone
        
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_token_created = timezone.now()
        user.save(update_fields=['reset_token', 'reset_token_created'])
        
        # TODO: Envoyer l'email avec le lien de réinitialisation
        # Pour le développement, on retourne le token
        reset_link = f"http://localhost:5173/reset-password?token={token}"
        
        return Response({
            'message': 'Un email de réinitialisation a été envoyé',
            'reset_link': reset_link,  # En développement seulement
            'token': token  # En développement seulement
        }, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    """
    Confirmation de réinitialisation de mot de passe
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        token = request.data.get('token')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')
        
        if not token or not new_password:
            return Response({'error': 'Token et nouveau mot de passe requis'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        if new_password != confirm_password:
            return Response({'error': 'Les mots de passe ne correspondent pas'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(reset_token=token)
            
            # Vérifier si le token n'a pas expiré (24h)
            from django.utils import timezone
            if user.reset_token_created:
                expiration = user.reset_token_created + timezone.timedelta(hours=24)
                if timezone.now() > expiration:
                    return Response({'error': 'Token expiré'}, 
                                  status=status.HTTP_400_BAD_REQUEST)
            
            # Réinitialiser le mot de passe
            user.set_password(new_password)
            
            # Si c'était un utilisateur externe, le rendre actif
            if user.is_external:
                user.is_external = False
                user.is_active = True
            
            user.reset_token = None
            user.reset_token_created = None
            user.save()
            
            return Response({
                'message': 'Mot de passe réinitialisé avec succès',
                'can_login': True
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response({'error': 'Token invalide'}, 
                          status=status.HTTP_400_BAD_REQUEST)


# ─── User ─────────────────────────────────────────────────────────────────────

class UserViewSet(viewsets.ModelViewSet):
    queryset           = User.objects.all()
    serializer_class   = UserSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['username', 'email', 'first_name', 'last_name']
    ordering_fields    = ['username', 'created_at']
    ordering           = ['-created_at']

    def get_permissions(self):
        if self.action in ['list', 'destroy', 'update', 'partial_update']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """GET /api/users/me/ — profil de l'utilisateur connecté"""
        return Response(UserSerializer(request.user).data)

    @action(detail=False, methods=['patch'], permission_classes=[IsAuthenticated])
    def update_profile(self, request):
        """PATCH /api/users/update_profile/"""
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def activate(self, request, pk=None):
        """POST /api/users/{id}/activate/"""
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=['is_active'])
        return Response({'detail': f'{user.username} activé.'})

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def deactivate(self, request, pk=None):
        """POST /api/users/{id}/deactivate/"""
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=['is_active'])
        return Response({'detail': f'{user.username} désactivé.'})


# ─── Researcher ───────────────────────────────────────────────────────────────
# ... (le reste de votre code ResearcherViewSet reste identique)
# ─── Researcher ───────────────────────────────────────────────────────────────
from data_pipeline.link_researcher_publications import link_by_name, link_by_orcid, check_and_sync_missing_publications

class ResearcherViewSet(viewsets.ModelViewSet):
    queryset           = Researcher.objects.select_related('user')
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields   = ['research_field']
    search_fields      = ['user__username', 'user__first_name', 'user__last_name', 'orcid']
    ordering_fields    = ['h_index']
    ordering           = ['-h_index']

    def get_serializer_class(self):
        if self.action in ['update', 'partial_update', 'update_profile', 'save_orcid']:
            return ResearcherUpdateSerializer
        return ResearcherSerializer
    

    def get_permissions(self):
        if self.action == 'destroy':
            return [IsAdminUser()]
        return [IsAuthenticated()]
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """GET /api/researchers/{id}/stats/"""
        researcher = self.get_object()
        return Response({
            'h_index':         researcher.h_index,
            'pub_count':       researcher.user.coauthored_publications.count(),
            'orcid':           researcher.orcid,
            'research_field':  researcher.research_field,
            'total_citations': sum(
                ca.publication.citation_count
                for ca in researcher.user.coauthored_publications
                                        .select_related('publication')
            ),
        })

    @action(detail=True, methods=['post'])
    def recalculate_h_index(self, request, pk=None):
        """POST /api/researchers/{id}/recalculate_h_index/"""
        researcher = self.get_object()
        new_h      = researcher.calculate_h_index()
        return Response({'h_index': new_h})
    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        researcher = request.user.researcher_profile
        serializer = self.get_serializer(researcher)
        return Response(serializer.data)
    @action(detail=True, methods=['post'])
    def link_publications(self, request, pk=None):
        """
        Endpoint pour lier manuellement les publications d'un chercheur
        POST /api/researchers/{id}/link_publications/
        """
        researcher = self.get_object()
        
        if not researcher.orcid:
            return Response(
                {"error": "Ce chercheur n'a pas d'ORCID"},
                status=400
            )
        
        try:
            stats = link_researcher_publications(
                researcher.user, 
                researcher.orcid
            )
            
            return Response({
                "message": "Publications liées avec succès",
                "stats": stats
            })
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=500
            )

    # ========== NOUVELLES ACTIONS POUR OPENALEX ==========

    @action(detail=True, methods=['post'], url_path='verify-orcid')
    def verify_orcid(self, request, pk=None):
        """
        POST /api/researchers/{id}/verify-orcid/
        Vérifie un ORCID sur OpenAlex sans le sauvegarder
        Body : { "orcid": "0000-0002-1825-0097" }
        """
        researcher = self.get_object()
        orcid = request.data.get('orcid', '').strip()

        # Vérifier que c'est le chercheur lui-même ou un admin
        if request.user.user_id != researcher.user.id and not request.user.is_staff:
            return Response(
                {'error': 'Vous ne pouvez vérifier que votre propre ORCID.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if not orcid:
            return Response(
                {'error': 'ORCID requis.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Nettoyer l'URL si besoin
        if "orcid.org/" in orcid:
            orcid = orcid.split("orcid.org/")[-1].strip()

        # Vérifier doublon (sauf si c'est le même chercheur)
        if Researcher.objects.filter(orcid=orcid).exclude(pk=researcher.pk).exists():
            return Response(
                {'valid': False, 'error': 'Cet ORCID est déjà associé à un autre compte.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Vérification OpenAlex
        result = verify_orcid(orcid)
        if not result['valid']:
            return Response(
                {'valid': False, 'error': result['error']},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response({
            'valid': True,
            'message': 'ORCID vérifié avec succès sur OpenAlex.',
            'profile': result['profile']
        })

    @action(detail=True, methods=['post'], url_path='save-orcid')
    def save_orcid(self, request, pk=None):
        """
        POST /api/researchers/{id}/save-orcid/
        Sauvegarde l'ORCID et lance la synchronisation des publications
        Body : { "orcid": "0000-0002-1825-0097" }
        """
        researcher = self.get_object()
        orcid = request.data.get('orcid', '').strip()

        # Vérifier que c'est le chercheur lui-même ou un admin
        if request.user.id != researcher.user.id and not request.user.is_staff:
            return Response(
                {'error': 'Vous ne pouvez modifier que votre propre ORCID.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if not orcid:
            return Response(
                {'error': 'ORCID requis.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Nettoyer l'URL si besoin
        if "orcid.org/" in orcid:
            orcid = orcid.split("orcid.org/")[-1].strip()

        # Vérifier doublon
        if Researcher.objects.filter(orcid=orcid).exclude(pk=researcher.pk).exists():
            return Response(
                {'error': 'Cet ORCID est déjà associé à un autre compte.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Vérification finale OpenAlex
        result = verify_orcid(orcid)
        if not result['valid']:
            return Response(
                {'valid': False, 'error': result['error']},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Sauvegarder l'ORCID
        old_orcid = researcher.orcid
        researcher.orcid = orcid
        researcher.save(update_fields=['orcid'])

        # Mettre à jour h_index si disponible
        h_index = result['profile'].get('h_index', 0)
        if h_index:
            researcher.h_index = h_index
            researcher.save(update_fields=['h_index'])

        # ========== NOUVEAU: Utiliser link_by_orcid avec auto_sync ==========
        try:
            # Utiliser la nouvelle fonction avec auto_sync_missing=True
            stats = link_by_orcid(researcher.user, orcid, auto_sync_missing=True)
            
            # Récupérer les statistiques de synchronisation
            sync_stats = {
                'publications_linked': stats.get('publications_linked', 0),
                'publications_total': stats.get('publications_total', 0),
                'coauthors_updated': stats.get('coauthors_updated', 0),
            }
            
            # Ajouter les stats des publications manquantes si disponibles
            if stats.get('missing_sync'):
                sync_stats['missing_publications_found'] = stats['missing_sync'].get('missing_count', 0)
                sync_stats['missing_publications_imported'] = stats['missing_sync'].get('imported_count', 0)
            
        except Exception as e:
            logger.error(f"Erreur sync ORCID {orcid}: {e}")
            sync_stats = {'error': str(e), 'publications_linked': 0}

        return Response({
            'message': 'ORCID sauvegardé avec succès.',
            'orcid': orcid,
            'old_orcid': old_orcid,
            'profile': result['profile'],
            'sync_stats': {
                'publications_linked': sync_stats.get('publications_linked', 0),
                'publications_total': sync_stats.get('publications_total', 0),
                'coauthors_updated': sync_stats.get('coauthors_updated', 0),
                'missing_publications_found': sync_stats.get('missing_publications_found', 0),
                'missing_publications_imported': sync_stats.get('missing_publications_imported', 0),
                'h_index': researcher.h_index,
            }
        })

    @action(detail=True, methods=['post'], url_path='sync-publications')
    def sync_publications(self, request, pk=None):
        """
        POST /api/researchers/{id}/sync-publications/
        Relance la synchronisation des publications depuis OpenAlex
        """
        researcher = self.get_object()

        # Vérifier que c'est le chercheur lui-même ou un admin
        if request.user.id != researcher.user.id and not request.user.is_staff:
            return Response(
                {'error': 'Vous ne pouvez synchroniser que vos propres publications.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if not researcher.orcid:
            return Response(
                {'error': 'Aucun ORCID associé à ce chercheur.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Lancer la synchronisation
        stats = sync_researcher(researcher.orcid)

        return Response({
            'message': 'Synchronisation terminée.',
            'orcid': researcher.orcid,
            'stats': {
                'publications_created': stats.get('created', 0),
                'publications_updated': stats.get('updated', 0),
                'h_index': researcher.h_index,
            }
        })

    @action(detail=True, methods=['post'], url_path='remove-orcid')
    def remove_orcid(self, request, pk=None):
        """
        POST /api/researchers/{id}/remove-orcid/
        Supprime l'ORCID du chercheur
        """
        researcher = self.get_object()

        # Vérifier que c'est le chercheur lui-même ou un admin
        if request.user.id != researcher.user.id and not request.user.is_staff:
            return Response(
                {'error': 'Vous ne pouvez supprimer que votre propre ORCID.'},
                status=status.HTTP_403_FORBIDDEN
            )

        old_orcid = researcher.orcid
        researcher.orcid = None
        researcher.h_index = 0
        researcher.save(update_fields=['orcid', 'h_index'])

        return Response({
            'message': 'ORCID supprimé avec succès.',
            'old_orcid': old_orcid
        })

    @action(detail=False, methods=['get'], url_path='me/stats')
    def my_stats(self, request):
        """
        GET /api/users/researchers/me/stats/
        Statistiques du chercheur connecté
        """
        try:
            researcher = request.user.researcher_profile
        except Researcher.DoesNotExist:
            return Response(
                {'error': 'Vous n\'avez pas de profil chercheur.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Récupérer les publications du chercheur
        publications = researcher.publications.all()
        
        # Nombre de publications
        pub_count = publications.count()
        
        # Total des citations
        total_citations = publications.aggregate(total=models.Sum('citation_count'))['total'] or 0
        
        # ✅ Compter TOUS les co-auteurs uniques (sans filtrer linked_user)
        from coAuthor.models import CoAuthor
        collaborators_count = CoAuthor.objects.filter(
            publication__in=publications
        ).exclude(
            # Exclure le chercheur lui-même (optionnel)
            linked_user=request.user
        ).values('author_name').distinct().count()
        
        return Response({
            'h_index': researcher.h_index,
            'pub_count': pub_count,
            'orcid': researcher.orcid,
            'research_field': researcher.research_field,
            'total_citations': total_citations,
            'collaborators_count': collaborators_count,
        })

    @action(detail=False, methods=['patch'], url_path='me/update-profile')
    def update_my_profile(self, request):
        """
        PATCH /api/researchers/me/update-profile/
        Met à jour le profil du chercheur connecté
        """
        try:
            researcher = request.user.researcher_profile
        except Researcher.DoesNotExist:
            return Response(
                {'error': 'Vous n\'avez pas de profil chercheur.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = ResearcherUpdateSerializer(
            researcher, 
            data=request.data, 
            partial=True,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)
    @action(detail=True, methods=['post'], url_path='connect-orcid')
    def connect_orcid(self, request, pk=None):
        """
        POST /api/researchers/{id}/connect-orcid/
        Vérifie l'ORCID puis synchronise automatiquement les données OpenAlex
        """

        researcher = self.get_object()
        orcid = request.data.get("orcid", "").strip()

        # sécurité
        if request.user.id != researcher.user.id and not request.user.is_staff:
            return Response(
                {"error": "Vous ne pouvez modifier que votre propre ORCID."},
                status=status.HTTP_403_FORBIDDEN
            )

        if not orcid:
            return Response(
                {"error": "ORCID requis."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # nettoyage
        if "orcid.org/" in orcid:
            orcid = orcid.split("orcid.org/")[-1].strip()

        # vérifier doublon
        if Researcher.objects.filter(orcid=orcid).exclude(pk=researcher.pk).exists():
            return Response(
                {"error": "Cet ORCID est déjà utilisé."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ─── Vérification OpenAlex ───
        result = verify_orcid(orcid)

        if not result["valid"]:
            return Response(
                {"error": result["error"]},
                status=status.HTTP_400_BAD_REQUEST
            )

        profile = result["profile"]

        # ─── Sauvegarder ORCID ───
        researcher.orcid = orcid
        researcher.h_index = profile.get("h_index", 0)
        researcher.save(update_fields=["orcid", "h_index"])

        # ========== NOUVEAU: Utiliser link_by_orcid avec auto_sync ==========
        try:
            # Utiliser la nouvelle fonction avec auto_sync_missing=True
            stats = link_by_orcid(researcher.user, orcid, auto_sync_missing=True)
            
            sync_result = {
                "publications_linked": stats.get("publications_linked", 0),
                "publications_total": stats.get("publications_total", 0),
                "coauthors_updated": stats.get("coauthors_updated", 0),
            }
            
            # Ajouter les stats des publications manquantes
            if stats.get("missing_sync"):
                sync_result["missing_publications_found"] = stats["missing_sync"].get("missing_count", 0)
                sync_result["missing_publications_imported"] = stats["missing_sync"].get("imported_count", 0)
                sync_result["openalex_total"] = stats["missing_sync"].get("openalex_count", 0)
                sync_result["local_total_before"] = stats["missing_sync"].get("local_count", 0)
            
        except Exception as e:
            logger.error(f"Erreur sync ORCID {orcid}: {e}")
            return Response(
                {"error": f"Erreur lors de la synchronisation: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response({
            "message": "ORCID connecté et synchronisé avec succès.",
            "profile": profile,
            "sync": {
                "publications_linked": sync_result.get("publications_linked", 0),
                "publications_total": sync_result.get("publications_total", 0),
                "coauthors_updated": sync_result.get("coauthors_updated", 0),
                "missing_publications_found": sync_result.get("missing_publications_found", 0),
                "missing_publications_imported": sync_result.get("missing_publications_imported", 0),
                "openalex_total": sync_result.get("openalex_total", 0),
                "local_total_before": sync_result.get("local_total_before", 0),
                "h_index": researcher.h_index,
            }
        })

    @action(detail=True, methods=['post'], url_path='sync-missing')
    def sync_missing_publications(self, request, pk=None):
        """
        POST /api/researchers/{id}/sync-missing/
        Vérifie et synchronise les publications manquantes entre 2010 et 2026
        """
        researcher = self.get_object()

        # Vérifier que c'est le chercheur lui-même ou un admin
        if request.user.id != researcher.user.id and not request.user.is_staff:
            return Response(
                {'error': 'Vous ne pouvez synchroniser que vos propres publications.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Utiliser la fonction de synchronisation des publications manquantes
        from data_pipeline.link_researcher_publications import check_and_sync_missing_publications
        
        try:
            stats = check_and_sync_missing_publications(
                researcher.user, 
                start_year=2010, 
                end_year=2026
            )
            
            return Response({
                'message': 'Synchronisation des publications manquantes terminée.',
                'stats': {
                    'openalex_count': stats.get('openalex_count', 0),
                    'local_count': stats.get('local_count', 0),
                    'missing_count': stats.get('missing_count', 0),
                    'imported_count': stats.get('imported_count', 0),
                    'errors': stats.get('errors', 0),
                },
                'is_synced': stats.get('missing_count', 0) == 0
            })
            
        except Exception as e:
            logger.error(f"Erreur sync missing publications: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_researchers(request):
    """
    GET /api/users/researchers/all/
    Récupère tous les chercheurs pour la gestion d'équipe
    """
    try:
        researchers = Researcher.objects.select_related('user').all()
        
        # Construction explicite du tableau
        data = []
        for researcher in researchers:
            if researcher.user:  # Vérifier que l'utilisateur existe
                data.append({
                    'user_id': researcher.user.user_id,
                    'username': researcher.user.username,
                    'email': researcher.user.email,
                    'first_name': researcher.user.first_name,
                    'last_name': researcher.user.last_name,
                    'full_name': f"{researcher.user.first_name} {researcher.user.last_name}".strip() or researcher.user.username,
                    'h_index': researcher.h_index or 0,
                    'research_field': researcher.research_field or 'Non spécifié',
                    'publication_count': 0,
                })
        
        print(f"✅ get_all_researchers: {len(data)} chercheurs trouvés")  # Debug
        return Response(data)  # Retourne directement un tableau []
        
    except Exception as e:
        print(f"❌ Error in get_all_researchers: {e}")
        return Response([], status=200)  # Toujours retourner un tableau vide

# ─── Admin ────────────────────────────────────────────────────────────────────

class AdminViewSet(viewsets.ModelViewSet):
    queryset           = Admin.objects.select_related('user')
    serializer_class   = AdminSerializer
    permission_classes = [IsAdminUser]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields   = ['role']
    search_fields      = ['user__username', 'user__email']


# ─── LabManager ───────────────────────────────────────────────────────────────

class LabManagerViewSet(viewsets.ModelViewSet):
    queryset           = LabManager.objects.select_related('user', 'laboratory')
    serializer_class   = LabManagerSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields   = ['laboratory']
    search_fields      = ['user__username', 'user__first_name', 'user__last_name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]


# ─── TeamLeader ───────────────────────────────────────────────────────────────

class TeamLeaderViewSet(viewsets.ModelViewSet):
    queryset           = TeamLeader.objects.select_related('user', 'team')
    serializer_class   = TeamLeaderSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields   = ['team']
    search_fields      = ['user__username', 'user__first_name', 'user__last_name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def lab_manager_check(request):
    """
    GET /api/users/lab-manager-check/
    """
    user = request.user
    
    try:
        lab_manager = LabManager.objects.select_related(
            'user', 'laboratory', 'laboratory__institution'
        ).get(user=user)
        
        laboratory = lab_manager.laboratory
        
        # Compter les chercheurs du laboratoire
        researchers_count = Researcher.objects.filter(
            user__team_leader_profile__team__laboratory=laboratory
        ).distinct().count()
        
        # Compter les publications du laboratoire
        publications_count = 0
        try:
            from publication.models import Publication
            from coAuthor.models import CoAuthor
            
            # Récupérer tous les chercheurs associés au labo via les équipes
            lab_researchers = Researcher.objects.filter(
                user__team_leader_profile__team__laboratory=laboratory
            ).distinct()
            
            if lab_researchers.exists():
                # ✅ Correction: Utiliser 'coauthors' (pluriel) au lieu de 'coauthor'
                # ou utiliser le modèle CoAuthor directement
                publications_count = Publication.objects.filter(
                    coauthors__linked_user__researcher_profile__in=lab_researchers
                ).distinct().count()
                
        except ImportError:
            # Si le modèle Publication n'existe pas encore
            pass
        except Exception as e:
            logger.warning(f"Could not count publications: {e}")
        
        # Compter les équipes du laboratoire
        teams_count = 0
        try:
            from team.models import Team
            teams_count = Team.objects.filter(laboratory=laboratory).count()
        except ImportError:
            pass
        
        # Calculer les statistiques additionnelles si disponibles
        total_citations = 0
        avg_h_index = 0
        
        if lab_researchers.exists():
            # Calculer la moyenne du h-index
            h_indices = lab_researchers.values_list('h_index', flat=True)
            if h_indices:
                avg_h_index = sum(h_indices) / len(h_indices)
        
        return Response({
            'is_lab_manager': True,
            'lab_id': laboratory.ID,
            'laboratory': {
                'id': laboratory.ID,
                'name': laboratory.name,
                'description': getattr(laboratory, 'description', ''),
                'institution': {
                    'id': laboratory.institution.id if laboratory.institution else None,
                    'name': laboratory.institution.name if laboratory.institution else None,
                } if laboratory.institution else None
            },
            'user': {
                'id': user.user_id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'full_name': f"{user.first_name} {user.last_name}".strip() or user.username
            },
            'lab_stats': {
                'total_researchers': researchers_count,
                'total_publications': publications_count,
                'total_teams': teams_count,
                'total_citations': total_citations,
                'avg_h_index': round(avg_h_index, 1) if avg_h_index else 0
            },
            'start_date': lab_manager.start_date.isoformat() if lab_manager.start_date else None,
            'end_date': lab_manager.end_date.isoformat() if lab_manager.end_date else None,
            'is_active': not lab_manager.end_date or lab_manager.end_date >= timezone.now().date()
        })
        
    except LabManager.DoesNotExist:
        return Response({
            'is_lab_manager': False,
            'message': 'Cet utilisateur n\'est pas un gestionnaire de laboratoire',
            'error': 'NO_LAB_MANAGER_ACCESS',
            'user_id': user.user_id,
            'username': user.username
        }, status=status.HTTP_403_FORBIDDEN)
    
    except Exception as e:
        logger.error(f"Erreur dans lab_manager_check: {e}", exc_info=True)
        return Response({
            'is_lab_manager': False,
            'message': f'Erreur lors de la vérification: {str(e)}',
            'error': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
 
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def lab_manager_login(request):
    """
    POST /api/users/lab-manager-login/
    
    Endpoint de "login" pour les gestionnaires de laboratoire
    Vérifie l'accès et retourne les données du laboratoire
    
    Utile pour les workflows où on veut vérifier explicitement l'accès
    """
    user = request.user
    
    try:
        lab_manager = LabManager.objects.select_related(
            'user', 'laboratory'
        ).get(user=user)
        
        # Vérifier si le mandat est toujours actif
        if lab_manager.end_date:
            from django.utils import timezone
            if lab_manager.end_date < timezone.now().date():
                return Response({
                    'success': False,
                    'message': 'Votre mandat de gestionnaire de laboratoire a expiré',
                    'error': 'MANDATE_EXPIRED',
                    'end_date': lab_manager.end_date.isoformat()
                }, status=status.HTTP_403_FORBIDDEN)
        
        laboratory = lab_manager.laboratory
        
        return Response({
            'success': True,
            'message': f'Bienvenue, {user.first_name}! Vous avez accès au laboratoire {laboratory.name}',
            'lab_id': laboratory.id,
            'lab_name': laboratory.name,
            'user': {
                'id': user.user_id,
                'username': user.username,
                'full_name': f"{user.first_name} {user.last_name}".strip()
            }
        }, status=status.HTTP_200_OK)
        
    except LabManager.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Accès refusé. Vous n\'avez pas les droits de gestionnaire de laboratoire.',
            'error': 'FORBIDDEN'
        }, status=status.HTTP_403_FORBIDDEN)
    
    except Exception as e:
        logger.error(f"Erreur dans lab_manager_login: {e}")
        return Response({
            'success': False,
            'message': f'Erreur serveur: {str(e)}',
            'error': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    
#──────────────────────────────────────── ────────────────────────────────────────
from users.models import InstitutionDirector
from users.serializers import InstitutionDirectorSerializer

class InstitutionDirectorViewSet(viewsets.ModelViewSet):
    queryset = InstitutionDirector.objects.select_related('user', 'institution')
    serializer_class = InstitutionDirectorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['institution']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]
@api_view(['POST'])
@permission_classes([AllowAny])
def institution_login(request):
    """
    POST /api/users/institution-login/
    Login pour les directeurs d'institution
    """
    from django.contrib.auth import authenticate
    from django.utils import timezone
    
    username = request.data.get('username')
    password = request.data.get('password')
    
    if not username or not password:
        return Response({
            'success': False,
            'error': 'Veuillez fournir un nom d\'utilisateur et un mot de passe'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Authentifier l'utilisateur
    user = authenticate(username=username, password=password)
    
    if not user:
        return Response({
            'success': False,
            'error': 'Nom d\'utilisateur ou mot de passe incorrect'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    if not user.is_active:
        return Response({
            'success': False,
            'error': 'Votre compte est désactivé. Veuillez contacter un administrateur.'
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Vérifier si l'utilisateur est directeur d'institution
    try:
        director = InstitutionDirector.objects.select_related(
            'user', 'institution'
        ).get(user=user)
        
        institution = director.institution
        
        # Vérifier si le mandat est toujours actif
        if director.end_date and director.end_date < timezone.now().date():
            return Response({
                'success': False,
                'error': 'Votre mandat de directeur a expiré',
                'end_date': director.end_date.isoformat()
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Générer ou récupérer le token JWT
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'success': True,
            'message': f'Bienvenue {user.get_full_name() or user.username}',
            'user': {
                'id': user.user_id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'full_name': user.get_full_name() or user.username,
                'role': 'institution_director'
            },
            'institution': {
                'id': institution.id,
                'name': institution.name,
                'type': institution.type,
                'type_display': institution.get_type_display(),
                'description': institution.description,
                'website': institution.website,
            },
            'tokens': {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            },
            'director_info': {
                'start_date': director.start_date.isoformat() if director.start_date else None,
                'end_date': director.end_date.isoformat() if director.end_date else None,
            }
        }, status=status.HTTP_200_OK)
        
    except InstitutionDirector.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Vous n\'êtes pas autorisé à accéder à cet espace. Vous devez être directeur d\'institution.',
            'role_check': 'institution_director_required'
        }, status=status.HTTP_403_FORBIDDEN)
    
    except Exception as e:
        logger.error(f"Erreur lors du login institution: {e}")
        return Response({
            'success': False,
            'error': 'Une erreur est survenue lors de la connexion'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def institution_director_check(request):
    """
    GET /api/users/institution-director-check/
    Vérifie si l'utilisateur connecté est directeur d'institution
    """
    user = request.user
    
    try:
        director = InstitutionDirector.objects.select_related(
            'user', 'institution'
        ).get(user=user)
        
        institution = director.institution
        
        return Response({
            'is_institution_director': True,
            'institution_id': institution.id,
            'institution': {
                'id': institution.id,
                'name': institution.name,
                'type': institution.type,
                'type_display': institution.get_type_display(),
                'description': institution.description,
                'website': institution.website,
            },
            'user': {
                'id': user.user_id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'full_name': user.get_full_name() or user.username
            },
            'director_info': {
                'start_date': director.start_date.isoformat() if director.start_date else None,
                'end_date': director.end_date.isoformat() if director.end_date else None,
                'is_active': not director.end_date or director.end_date >= timezone.now().date()
            }
        })
        
    except InstitutionDirector.DoesNotExist:
        return Response({
            'is_institution_director': False,
            'message': 'Vous n\'êtes pas directeur d\'institution',
        })
    
# users/views.py - Ajoutez ceci après institution_director_check

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_check(request):
    """
    GET /api/users/admin-check/
    Vérifie si l'utilisateur connecté a un profil Admin personnalisé
    """
    user = request.user
    
    try:
        admin_profile = Admin.objects.select_related('user').get(user=user)
        return Response({
            'is_admin': True,
            'role': admin_profile.role,
            'is_super_admin': admin_profile.is_super_admin,
            'user': {
                'id': user.user_id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            }
        })
    except Admin.DoesNotExist:
        return Response({
            'is_admin': False,
            'message': 'Cet utilisateur n\'a pas de profil administrateur'
        }, status=status.HTTP_403_FORBIDDEN)


# users/views.py - Ajoutez ces endpoints admin complets

# ========== ADMIN DASHBOARD ENDPOINTS ==========

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsCustomAdmin])
def admin_dashboard_stats(request):
    """Statistiques complètes pour le dashboard admin"""
    from django.db.models import Count, Sum
    from institution.models import Institution
    from laboratory.models import Laboratory
    from team.models import Team
    from publication.models import Publication
    
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    inactive_users = User.objects.filter(is_active=False).count()
    total_researchers = Researcher.objects.count()
    total_institutions = Institution.objects.count()
    total_laboratories = Laboratory.objects.count()
    total_teams = Team.objects.count()
    total_publications = Publication.objects.count()
    
    # Calculer le total des citations
    total_citations = Publication.objects.aggregate(total=Sum('citation_count'))['total'] or 0
    
    # Moyenne du h-index
    avg_h_index = Researcher.objects.aggregate(avg=models.Avg('h_index'))['avg'] or 0
    
    return Response({
        'total_users': total_users,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'total_researchers': total_researchers,
        'total_institutions': total_institutions,
        'total_laboratories': total_laboratories,
        'total_teams': total_teams,
        'total_publications': total_publications,
        'total_citations': total_citations,
        'avg_h_index': round(avg_h_index, 1),
    })


# ========== ADMIN INSTITUTIONS MANAGEMENT ==========

@api_view(['GET', 'POST', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsCustomAdmin])
def admin_institutions(request, institution_id=None):
    """
    GET /api/admin/institutions/ - Liste toutes les institutions
    POST /api/admin/institutions/ - Crée une institution
    GET /api/admin/institutions/{id}/ - Détail d'une institution
    PUT /api/admin/institutions/{id}/ - Modifie une institution
    DELETE /api/admin/institutions/{id}/ - Supprime une institution
    """
    from institution.models import Institution
    from institution.serializers import InstitutionSerializer
    
    if request.method == 'GET':
        if institution_id:
            try:
                institution = Institution.objects.get(id=institution_id)
                serializer = InstitutionSerializer(institution)
                return Response(serializer.data)
            except Institution.DoesNotExist:
                return Response({'error': 'Institution non trouvée'}, status=404)
        else:
            institutions = Institution.objects.all()
            serializer = InstitutionSerializer(institutions, many=True)
            return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = InstitutionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)
    
    elif request.method == 'PUT':
        try:
            institution = Institution.objects.get(id=institution_id)
            serializer = InstitutionSerializer(institution, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=400)
        except Institution.DoesNotExist:
            return Response({'error': 'Institution non trouvée'}, status=404)
    
    elif request.method == 'DELETE':
        try:
            institution = Institution.objects.get(id=institution_id)
            institution.delete()
            return Response({'message': 'Institution supprimée'}, status=200)
        except Institution.DoesNotExist:
            return Response({'error': 'Institution non trouvée'}, status=404)


# ========== ADMIN LABORATORIES MANAGEMENT ==========

@api_view(['GET', 'POST', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsCustomAdmin])
def admin_laboratories(request, lab_id=None):
    """
    GET /api/admin/laboratories/ - Liste tous les laboratoires
    POST /api/admin/laboratories/ - Crée un laboratoire
    GET /api/admin/laboratories/{id}/ - Détail d'un laboratoire
    PUT /api/admin/laboratories/{id}/ - Modifie un laboratoire
    DELETE /api/admin/laboratories/{id}/ - Supprime un laboratoire
    GET /api/admin/laboratories/{id}/teams/ - Liste les équipes d'un laboratoire
    GET /api/admin/laboratories/{id}/members/ - Liste les membres d'un laboratoire
    """
    from laboratory.models import Laboratory
    from laboratory.serializers import LaboratorySerializer
    from team.models import Team
    from team.serializers import TeamSerializer
    from users.serializers import UserSerializer
    
    if request.method == 'GET':
        if lab_id:
            try:
                laboratory = Laboratory.objects.get(ID=lab_id)
                
                # Si demande les équipes
                if 'teams' in request.path:
                    teams = Team.objects.filter(laboratory=laboratory)
                    serializer = TeamSerializer(teams, many=True)
                    return Response(serializer.data)
                
                # Si demande les membres
                elif 'members' in request.path:
                    members = User.objects.filter(
                        team_leader_profile__team__laboratory=laboratory
                    ).distinct()
                    serializer = UserSerializer(members, many=True)
                    return Response(serializer.data)
                
                # Détail du laboratoire
                else:
                    serializer = LaboratorySerializer(laboratory)
                    return Response(serializer.data)
                    
            except Laboratory.DoesNotExist:
                return Response({'error': 'Laboratoire non trouvé'}, status=404)
        else:
            laboratories = Laboratory.objects.all()
            serializer = LaboratorySerializer(laboratories, many=True)
            return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = LaboratorySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)
    
    elif request.method == 'PUT':
        try:
            laboratory = Laboratory.objects.get(ID=lab_id)
            serializer = LaboratorySerializer(laboratory, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=400)
        except Laboratory.DoesNotExist:
            return Response({'error': 'Laboratoire non trouvé'}, status=404)
    
    elif request.method == 'DELETE':
        try:
            laboratory = Laboratory.objects.get(ID=lab_id)
            laboratory.delete()
            return Response({'message': 'Laboratoire supprimé'}, status=200)
        except Laboratory.DoesNotExist:
            return Response({'error': 'Laboratoire non trouvé'}, status=404)


# ========== ADMIN TEAMS MANAGEMENT ==========

@api_view(['GET', 'POST', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsCustomAdmin])
def admin_teams(request, team_id=None):
    """
    GET /api/admin/teams/ - Liste toutes les équipes
    POST /api/admin/teams/ - Crée une équipe
    GET /api/admin/teams/{id}/ - Détail d'une équipe
    PUT /api/admin/teams/{id}/ - Modifie une équipe
    DELETE /api/admin/teams/{id}/ - Supprime une équipe
    GET /api/admin/teams/{id}/members/ - Liste les membres d'une équipe
    """
    from team.models import Team
    from team.serializers import TeamSerializer
    from users.serializers import UserSerializer
    
    if request.method == 'GET':
        if team_id:
            try:
                team = Team.objects.get(id=team_id)
                
                # Si demande les membres
                if 'members' in request.path:
                    members = User.objects.filter(team_leader_profile__team=team)
                    serializer = UserSerializer(members, many=True)
                    return Response(serializer.data)
                
                # Détail de l'équipe
                else:
                    serializer = TeamSerializer(team)
                    return Response(serializer.data)
                    
            except Team.DoesNotExist:
                return Response({'error': 'Équipe non trouvée'}, status=404)
        else:
            teams = Team.objects.all()
            serializer = TeamSerializer(teams, many=True)
            return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = TeamSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)
    
    elif request.method == 'PUT':
        try:
            team = Team.objects.get(id=team_id)
            serializer = TeamSerializer(team, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=400)
        except Team.DoesNotExist:
            return Response({'error': 'Équipe non trouvée'}, status=404)
    
    elif request.method == 'DELETE':
        try:
            team = Team.objects.get(id=team_id)
            team.delete()
            return Response({'message': 'Équipe supprimée'}, status=200)
        except Team.DoesNotExist:
            return Response({'error': 'Équipe non trouvée'}, status=404)


# ========== ADMIN RESEARCHERS MANAGEMENT ==========

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsCustomAdmin])
def admin_researchers(request, researcher_id=None):
    """
    GET /api/admin/researchers/ - Liste tous les chercheurs
    GET /api/admin/researchers/{id}/ - Détail d'un chercheur
    PUT /api/admin/researchers/{id}/ - Modifie un chercheur
    DELETE /api/admin/researchers/{id}/ - Supprime un chercheur
    GET /api/admin/researchers/{id}/publications/ - Liste les publications d'un chercheur
    """
    from users.serializers import ResearcherSerializer
    
    if request.method == 'GET':
        if researcher_id:
            try:
                researcher = Researcher.objects.get(id=researcher_id)
                
                # Si demande les publications
                if 'publications' in request.path:
                    publications = researcher.publications.all()
                    from publication.serializers import PublicationSerializer
                    serializer = PublicationSerializer(publications, many=True)
                    return Response(serializer.data)
                
                # Détail du chercheur
                else:
                    serializer = ResearcherSerializer(researcher)
                    return Response(serializer.data)
                    
            except Researcher.DoesNotExist:
                return Response({'error': 'Chercheur non trouvé'}, status=404)
        else:
            researchers = Researcher.objects.all()
            serializer = ResearcherSerializer(researchers, many=True)
            return Response(serializer.data)
    
    elif request.method == 'PUT':
        try:
            researcher = Researcher.objects.get(id=researcher_id)
            serializer = ResearcherSerializer(researcher, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=400)
        except Researcher.DoesNotExist:
            return Response({'error': 'Chercheur non trouvé'}, status=404)
    
    elif request.method == 'DELETE':
        try:
            researcher = Researcher.objects.get(id=researcher_id)
            user = researcher.user
            researcher.delete()
            user.delete()  # Supprime aussi l'utilisateur associé
            return Response({'message': 'Chercheur supprimé'}, status=200)
        except Researcher.DoesNotExist:
            return Response({'error': 'Chercheur non trouvé'}, status=404)


# ========== ADMIN PUBLICATIONS MANAGEMENT ==========
# users/views.py - Ajoutez cette ligne avec les autres imports
@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsCustomAdmin])
def admin_publications(request, pub_id=None):
    """
    GET /api/admin/publications/ - Liste toutes les publications
    GET /api/admin/publications/{id}/ - Détail d'une publication
    PUT /api/admin/publications/{id}/ - Modifie une publication
    DELETE /api/admin/publications/{id}/ - Supprime une publication
    """
    from publication.models import Publication
    from publication.serializers import PublicationSerializer
    
    if request.method == 'GET':
        if pub_id:
            try:
                publication = Publication.objects.get(id=pub_id)
                serializer = PublicationSerializer(publication)
                return Response(serializer.data)
            except Publication.DoesNotExist:
                return Response({'error': 'Publication non trouvée'}, status=404)
        else:
            publications = Publication.objects.all()
            serializer = PublicationSerializer(publications, many=True)
            return Response(serializer.data)
    
    elif request.method == 'PUT':
        try:
            publication = Publication.objects.get(id=pub_id)
            serializer = PublicationSerializer(publication, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=400)
        except Publication.DoesNotExist:
            return Response({'error': 'Publication non trouvée'}, status=404)
    
    elif request.method == 'DELETE':
        try:
            publication = Publication.objects.get(id=pub_id)
            publication.delete()
            return Response({'message': 'Publication supprimée'}, status=200)
        except Publication.DoesNotExist:
            return Response({'error': 'Publication non trouvée'}, status=404)


# ========== ADMIN USERS MANAGEMENT ==========

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def admin_users(request, user_id=None):
    """
    GET /api/admin/users/ - Liste tous les utilisateurs
    GET /api/admin/users/{id}/ - Détail d'un utilisateur
    PUT /api/admin/users/{id}/ - Modifie un utilisateur
    DELETE /api/admin/users/{id}/ - Supprime un utilisateur
    """
    # Vérifier si l'utilisateur est admin (profil Admin personnalisé)
    try:
        admin_profile = Admin.objects.get(user=request.user)
    except Admin.DoesNotExist:
        return Response({'error': 'Admin privileges required'}, status=status.HTTP_403_FORBIDDEN)
    
    if request.method == 'GET':
        if user_id:
            try:
                user = User.objects.get(user_id=user_id)
                # Ne pas permettre l'accès aux superusers
                if user.is_superuser:
                    return Response({'error': 'Cannot access superuser'}, status=403)
                serializer = UserSerializer(user)
                return Response(serializer.data)
            except User.DoesNotExist:
                return Response({'error': 'Utilisateur non trouvé'}, status=404)
        else:
            # Exclure les superusers
            users = User.objects.filter(is_superuser=False)
            serializer = UserSerializer(users, many=True)
            return Response(serializer.data)
    
    elif request.method == 'PUT':
        if not user_id:
            return Response({'error': 'User ID required'}, status=400)
        try:
            user = User.objects.get(user_id=user_id)
            if user.is_superuser:
                return Response({'error': 'Cannot modify superuser'}, status=403)
            serializer = UserSerializer(user, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=400)
        except User.DoesNotExist:
            return Response({'error': 'Utilisateur non trouvé'}, status=404)
    
    elif request.method == 'DELETE':
        if not user_id:
            return Response({'error': 'User ID required'}, status=400)
        try:
            user = User.objects.get(user_id=user_id)
            # Ne pas permettre la suppression des superusers
            if user.is_superuser:
                return Response({'error': 'Cannot delete superuser'}, status=403)
            # Ne pas permettre la suppression de son propre compte
            if user.user_id == request.user.user_id:
                return Response({'error': 'Cannot delete your own account'}, status=403)
            user.delete()
            return Response({'message': 'Utilisateur supprimé avec succès'}, status=200)
        except User.DoesNotExist:
            return Response({'error': 'Utilisateur non trouvé'}, status=404)
# users/views.py - Pour une API REST

from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import User, Researcher
from data_pipeline.link_researcher_publications import link_by_name, link_by_orcid


# users/views.py - Remplacez la fonction upgrade_to_researcher par celle-ci

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upgrade_to_researcher(request):
    """
    Endpoint pour upgrade un user en researcher
    Body: {
        "user_id": 123,
        "orcid": "0000-0000-0000-0000",
        "research_field": "Computer Science"
    }
    """
    # Vérifier que l'utilisateur est admin
    try:
        admin_profile = Admin.objects.get(user=request.user)
    except Admin.DoesNotExist:
        if not request.user.is_superuser:
            return Response({'error': 'Admin privileges required'}, status=status.HTTP_403_FORBIDDEN)
    
    # Récupérer l'ID de l'utilisateur à promouvoir
    user_id = request.data.get('user_id')
    if not user_id:
        return Response({'error': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Récupérer l'utilisateur
    try:
        target_user = User.objects.get(user_id=user_id)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Vérifier que l'utilisateur n'est pas déjà chercheur
    if hasattr(target_user, 'researcher_profile'):
        return Response({'error': 'User is already a researcher'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Récupérer les données optionnelles
    orcid = request.data.get('orcid', '').strip() or None
    research_field = request.data.get('research_field', '').strip()
    
    # Créer le chercheur
    researcher = Researcher.objects.create(
        user=target_user,
        orcid=orcid,
        research_field=research_field
    )
    
    # Si ORCID fourni, synchroniser les publications
    sync_stats = {}
    if orcid:
        try:
            # Vérifier l'ORCID sur OpenAlex
            from data_pipeline.openalex_verify import verify_orcid
            result = verify_orcid(orcid)
            
            if result['valid']:
                # Mettre à jour le h_index
                h_index = result.get('profile', {}).get('h_index', 0)
                if h_index:
                    researcher.h_index = h_index
                    researcher.save(update_fields=['h_index'])
                
                # Synchroniser les publications
                from data_pipeline.link_researcher_publications import link_by_orcid
                stats = link_by_orcid(target_user, orcid, auto_sync_missing=True)
                
                sync_stats = {
                    'publications_linked': stats.get('publications_linked', 0),
                    'publications_total': stats.get('publications_total', 0),
                    'coauthors_updated': stats.get('coauthors_updated', 0),
                }
                
                if stats.get('missing_sync'):
                    sync_stats['missing_publications_found'] = stats['missing_sync'].get('missing_count', 0)
                    sync_stats['missing_publications_imported'] = stats['missing_sync'].get('imported_count', 0)
            else:
                sync_stats = {'error': result.get('error', 'ORCID not found on OpenAlex')}
                
        except Exception as e:
            logger.error(f"Error syncing ORCID {orcid}: {e}")
            sync_stats = {'error': str(e)}
    
    # Retourner la réponse
    return Response({
        "message": f"User {target_user.username} promoted to researcher successfully",
        "researcher": {
            "id": researcher.id,
            "user_id": target_user.user_id,
            "username": target_user.username,
            "email": target_user.email,
            "first_name": target_user.first_name,
            "last_name": target_user.last_name,
            "orcid": researcher.orcid,
            "research_field": researcher.research_field,
            "h_index": researcher.h_index,
        },
        "sync_stats": sync_stats
    }, status=status.HTTP_201_CREATED)

# users/views.py - Version corrigée
class TeamLeaderCheckView(APIView):
    """
    Vérifie si l'utilisateur connecté est un Team Leader
    et retourne les informations de son équipe
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        # Vérifier si l'utilisateur est un Team Leader
        try:
            team_leader = TeamLeader.objects.select_related('team').get(user=user)
            
            # Récupérer l'ID de l'équipe - utilisez 'id' ou 'ID' selon votre modèle
            team = team_leader.team
            team_id = getattr(team, 'ID', None) or getattr(team, 'id', None)
            
            return Response({
                'is_team_leader': True,
                'team_id': team_id,
                'team_name': team.name,
                'user': {
                    'id': user.user_id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                }
            })
        except TeamLeader.DoesNotExist:
            return Response({
                'is_team_leader': False,
                'message': 'Cet utilisateur n\'est pas un Team Leader'
            }, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            logger.error(f"Erreur TeamLeaderCheckView: {e}")
            return Response({
                'is_team_leader': False,
                'message': f'Erreur lors de la vérification: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        


