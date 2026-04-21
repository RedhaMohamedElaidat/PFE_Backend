# users/serializers.py
import re
import logging
from rest_framework import serializers
from users.models import InstitutionDirector
from users.models import User, Admin, Researcher, LabManager, TeamLeader

logger = logging.getLogger(__name__)


# ─── User ─────────────────────────────────────────────────────────────────────

class UserSerializer(serializers.ModelSerializer):
    
    class Meta:
        model  = User
        fields = ['user_id', 'username', 'email', 'first_name', 'last_name',
                  'is_active', 'created_at', 'updated_at']
        read_only_fields = ['user_id', 'created_at', 'updated_at']


# ─── Register ─────────────────────────────────────────────────────────────────

class RegisterSerializer(serializers.ModelSerializer):
    password  = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True)
    role      = serializers.ChoiceField(
        choices=['researcher', 'admin','user'],
        default='user',
        write_only=True
    )
    # Champs optionnels pour le profil chercheur
    orcid = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
        write_only=True,
        help_text="ORCID du chercheur : XXXX-XXXX-XXXX-XXXX (optionnel)"
    )
    research_field = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
        write_only=True,
        help_text="Domaine de recherche (optionnel)"
    )

    class Meta:
        model  = User
        fields = [
            'username', 'email', 'password', 'password2',
            'first_name', 'last_name', 'role',
            'orcid', 'research_field',
        ]

    # ── Validations ───────────────────────────────────────────────────────

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError(
                {'password': 'Les mots de passe ne correspondent pas.'}
            )
        return attrs

    def validate_orcid(self, value):
        """Valide le format ORCID si fourni."""
        if not value or value.strip() == '':
            return ''

        # Nettoyer si l'utilisateur colle l'URL complète
        # ex : https://orcid.org/0000-0002-1825-0097
        if "orcid.org/" in value:
            value = value.split("orcid.org/")[-1].strip()

        # Valider le format XXXX-XXXX-XXXX-XXXX
        pattern = r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$'
        if not re.match(pattern, value):
            raise serializers.ValidationError(
                f"Format ORCID invalide : '{value}'. "
                "Attendu : XXXX-XXXX-XXXX-XXXX (ex: 0000-0002-1825-0097)"
            )

        # Vérifier doublon en base
        if Researcher.objects.filter(orcid=value).exists():
            raise serializers.ValidationError(
                "Cet ORCID est déjà associé à un autre compte."
            )

        return value

    # ── Création ──────────────────────────────────────────────────────────

    def create(self, validated_data):
        role           = validated_data.pop('role','user')
        orcid          = validated_data.pop('orcid', '').strip() or None
        research_field = validated_data.pop('research_field', '').strip()
        validated_data.pop('password2')

        # Créer l'utilisateur
        user = User.objects.create_user(**validated_data)

        if role == 'researcher':
            self._create_researcher(user, orcid, research_field)

        elif role == 'admin':
            Admin.objects.create(user=user)

        return user

    def _create_researcher(self, user, orcid: str, research_field: str):
        """
        Crée le profil Researcher et lance la sync OpenAlex si ORCID fourni.
        """
        researcher = Researcher.objects.create(
            user           = user,
            orcid          = orcid,
            research_field = research_field,
        )

        # Sync OpenAlex si ORCID fourni
        if orcid:
            self._sync_openalex(researcher, orcid)

    def _sync_openalex(self, researcher, orcid: str):
        """
        Vérifie l'ORCID sur OpenAlex et lance la sync des publications.
        Ne bloque pas l'inscription si la sync échoue.
        """
        try:
            from data_pipeline.openalex_verify import verify_orcid
            result = verify_orcid(orcid)

            if not result['valid']:
                logger.warning(
                    f"ORCID '{orcid}' non trouvé sur OpenAlex : {result['error']}"
                )
                return

            # Mettre à jour le h_index depuis OpenAlex
            h_index = result.get('profile', {}).get('h_index', 0)
            if h_index:
                researcher.h_index = h_index
                researcher.save(update_fields=['h_index'])

            # Lancer la sync des publications
            from data_pipeline.openalex_researcher_sync import sync_researcher
            stats = sync_researcher(orcid)

            logger.info(
                f"Sync ORCID {orcid} terminée : "
                f"{stats.get('created', 0)} créées, "
                f"{stats.get('updated', 0)} MAJ, "
                f"{stats.get('citations', 0)} citations"
            )

        except Exception as e:
            # Ne jamais bloquer l'inscription
            logger.error(f"Erreur sync ORCID {orcid} à l'inscription: {e}")


# ─── ChangePassword ───────────────────────────────────────────────────────────

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value


# ─── Researcher ───────────────────────────────────────────────────────────────

class ResearcherSerializer(serializers.ModelSerializer):
    user     = UserSerializer(read_only=True)
    h_index  = serializers.IntegerField(read_only=True)

    class Meta:
        model  = Researcher
        fields = ['id', 'user', 'orcid', 'research_field', 'h_index']


class ResearcherUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Researcher
        fields = ['orcid', 'research_field']

    def validate_orcid(self, value):
        if not value:
            return value

        if "orcid.org/" in value:
            value = value.split("orcid.org/")[-1].strip()

        from users.models import validate_orcid
        validate_orcid(value)

        # Vérifier doublon sauf pour le même researcher
        qs = Researcher.objects.filter(orcid=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Cet ORCID est déjà associé à un autre compte."
            )

        return value


# ─── Admin ────────────────────────────────────────────────────────────────────

class AdminSerializer(serializers.ModelSerializer):
    user         = UserSerializer(read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model  = Admin
        fields = ['id', 'user', 'role', 'role_display']


# ─── LabManager ───────────────────────────────────────────────────────────────

class LabManagerSerializer(serializers.ModelSerializer):
    user            = UserSerializer(read_only=True)
    laboratory_name = serializers.CharField(source='laboratory.name', read_only=True)

    class Meta:
        model  = LabManager
        fields = ['id', 'user', 'laboratory', 'laboratory_name', 'start_date', 'end_date']


# ─── TeamLeader ───────────────────────────────────────────────────────────────

class TeamLeaderSerializer(serializers.ModelSerializer):
    user      = UserSerializer(read_only=True)
    team_name = serializers.CharField(source='team.name', read_only=True)

    class Meta:
        model  = TeamLeader
        fields = ['id', 'user', 'team', 'team_name', 'start_date', 'end_date']

# ─── Institution Director ────────────────────────────────────────────────────

class InstitutionDirectorSerializer(serializers.ModelSerializer):
    user               = UserSerializer(read_only=True)
    institution_name   = serializers.CharField(source='institution.name', read_only=True)

    class Meta:
        model  = InstitutionDirector
        fields = [
            'id',
            'user',
            'institution',
            'institution_name',
            'start_date',
            'end_date'
        ]