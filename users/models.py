from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone
import re


# ─────────────────────────────────────────
# USER MANAGER
# ─────────────────────────────────────────
class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        if not email:
            raise ValueError("L'adresse email est obligatoire")

        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)  # 🔐 hash password
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if not extra_fields.get('is_staff'):
            raise ValueError('Superuser must have is_staff=True.')
        if not extra_fields.get('is_superuser'):
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(username, email, password, **extra_fields)


# ─────────────────────────────────────────
# USER MODEL
# ─────────────────────────────────────────
class User(AbstractUser):
    user_id = models.AutoField(primary_key=True)
    email = models.EmailField(unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    reset_token = models.CharField(max_length=255, blank=True, null=True)
    reset_token_created = models.DateTimeField(blank=True, null=True)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f"{self.username} - {self.email}"


# ─────────────────────────────────────────
# ADMIN ROLE
# ─────────────────────────────────────────
class AdminRole(models.TextChoices):
    SUPER_ADMIN = 'Super_Admin', 'Super Admin'
    DATA_MANAGER = 'Data_Manager', 'Data Manager'


class Admin(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
    role = models.CharField(max_length=20, choices=AdminRole.choices, default=AdminRole.DATA_MANAGER)

    class Meta:
        db_table = 'admins'

    @property
    def is_super_admin(self):
        return self.role == AdminRole.SUPER_ADMIN

    def __str__(self):
        return f"{self.user.username} ({self.role})"


# ─────────────────────────────────────────
# VALIDATOR ORCID
# ─────────────────────────────────────────
def validate_orcid(value):
    from django.core.exceptions import ValidationError
    pattern = r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$'
    if value and not re.match(pattern, value):
        raise ValidationError("Format ORCID invalide")


# ─────────────────────────────────────────
# RESEARCHER
# ─────────────────────────────────────────
class Researcher(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='researcher_profile')
    orcid = models.CharField(max_length=19, unique=True, blank=True, null=True, validators=[validate_orcid])
    research_field = models.CharField(max_length=255, blank=True)
    h_index = models.IntegerField(default=0)

    class Meta:
        db_table = 'researchers'

    def __str__(self):
        return f"{self.user.username} - {self.h_index}"
    
    def save(self, *args, **kwargs):
        """
        Override save pour lier automatiquement les publications
        quand un chercheur est créé
        """
        # Vérifier si c'est un nouvel enregistrement
        is_new = self.pk is None
        
        # Sauvegarder d'abord
        super().save(*args, **kwargs)
        
        # Si c'est un nouveau chercheur, lier les publications par son nom
        if is_new:
            from data_pipeline.link_researcher_publications import link_by_name
            # Lier par le nom complet de l'utilisateur
            link_by_name(self.user, self.user.get_full_name())
    def get_publications(self, start_year=None, end_year=None):
        """Récupère les publications du chercheur"""
        pubs = self.publications.all()
        if start_year:
            pubs = pubs.filter(publication_year__gte=start_year)
        if end_year:
            pubs = pubs.filter(publication_year__lte=end_year)
        return pubs
    
    def get_bibliometric_indicators(self, start_year=None, end_year=None):
        """Calcule tous les indicateurs bibliométriques pour ce chercheur"""
        from data_pipeline.bibliometrix_indicators import BibliometricIndicators
        
        pubs = self.get_publications(start_year, end_year)
        if not pubs.exists():
            return None
        
        indicators = BibliometricIndicators(pubs)
        
        return {
            'production': {
                'total': indicators.total_publications(),
                'by_year': indicators.publications_by_year(),
                'growth_rate': indicators.annual_growth_rate(),
            },
            'impact': {
                'total_citations': indicators.total_citations(),
                'avg_citations': indicators.avg_citations_per_paper(),
                'h_index': indicators.h_index(self.user.get_full_name()),
                'most_cited': indicators.most_cited_papers(10),
            },
            'collaboration': {
                'avg_coauthors': indicators.avg_coauthors_per_paper(),
                'single_author': indicators.single_author_papers(),
            }
        }
    
    def update_h_index(self):
        """Met à jour le H-index du chercheur"""
        from data_pipeline.bibliometrix_indicators import update_researcher_h_index
        return update_researcher_h_index(self.id)
# ─────────────────────────────────────────
# LAB MANAGER
# ─────────────────────────────────────────
class LabManager(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='lab_manager_profile')
    laboratory = models.ForeignKey('laboratory.Laboratory', on_delete=models.CASCADE)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(blank=True, null=True)

    class Meta:
        db_table = 'lab_managers'


# ─────────────────────────────────────────
# TEAM LEADER
# ─────────────────────────────────────────
class TeamLeader(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='team_leader_profile')
    team = models.ForeignKey('team.Team', on_delete=models.CASCADE)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(blank=True, null=True)

    class Meta:
        db_table = 'team_leaders'

# ─────────────────────────────────────────
# INSTITUTION DIRECTOR
# ─────────────────────────────────────────
class InstitutionDirector(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='institution_director_profile')
    institution = models.ForeignKey('institution.Institution', on_delete=models.CASCADE)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(blank=True, null=True)

    class Meta:
        db_table = 'institution_directors'