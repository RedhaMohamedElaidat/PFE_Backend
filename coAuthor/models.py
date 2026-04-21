from django.db import models
from publication.models import Publication
from users.models import User

# Create your models here.
class CoAuthor(models.Model):
    """
    تمثيل المؤلف المشارك في منشور
    Représentation d'un co-auteur dans une publication
    
    NOT linked directly to User - only stores authorship metadata
    Pas de lien direct vers User - stocke seulement les métadonnées d'authorship
    """
    ID = models.AutoField(primary_key=True)
    
    # ── Publication (required) ────────────────────────────────────────────
    publication = models.ForeignKey(
        Publication, 
        on_delete=models.CASCADE, 
        related_name='coauthors'
    )
    
    # ── Author Information from OpenAlex ──────────────────────────────────
    author_name = models.CharField(
        max_length=255,
        help_text="اسم المؤلف من OpenAlex / Nom de l'auteur depuis OpenAlex"
    )
    
    author_orcid = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        db_index=True,
        help_text="ORCID ID if available / ORCID ID s'il est disponible"
    )
    
    openalex_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="OpenAlex author ID / ID auteur OpenAlex"
    )
    
    # ── Authorship Metadata ───────────────────────────────────────────────
    contribution_type = models.IntegerField(
        choices=[
            (1, 'First Author'),
            (2, 'Second Author'),
            (3, 'Third Author'),
            (4, 'Corresponding Author'),
            (5, 'Other')
        ],
        default=1
    )
    
    author_order = models.IntegerField(
        default=1,
        help_text="ترتيب المؤلف في المنشور / Ordre de l'auteur dans la publication"
    )
    
    affiliation_at_time = models.CharField(
        max_length=255,
        blank=True,
        help_text="انتماء المؤلف وقت النشر / Affiliation au moment de la publication"
    )
    
    # ── OPTIONAL: Link to registered User ──────────────────────────────────
    # This is populated ONLY when a user registers with matching ORCID
    # هذا يُملأ فقط عندما يسجل مستخدم برنامج ORCID مطابق
    linked_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='coauthor_credits',
        help_text="Link to User if they registered / الارتباط بـ User إذا تسجلوا"
    )
    
    # ── Timestamps ────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'coauthors'
        verbose_name = 'CoAuthor'
        verbose_name_plural = 'CoAuthors'
        
        indexes = [
            models.Index(fields=['author_orcid', 'publication']),
            models.Index(fields=['linked_user']),
            models.Index(fields=['openalex_id']),
        ]
        ordering = ['author_order']

    def __str__(self):
        """
        Display representation
        """
        user_info = ""
        if self.linked_user:
            user_info = f" (User: {self.linked_user.email})"
        
        return f"{self.author_name} - {self.publication.title[:30]}{user_info}"
    
    @property
    def is_registered(self):
        """
        Check if this co-author has registered as a system user
        التحقق مما إذا كان هذا المؤلف المشارك قد سجل كمستخدم في النظام
        """
        return self.linked_user is not None
    
    @property
    def display_name(self):
        """
        Get user name if registered, otherwise use author_name from OpenAlex
        احصل على اسم المستخدم إذا تم تسجيله، وإلا استخدم author_name من OpenAlex
        """
        if self.linked_user:
            return self.linked_user.get_full_name()
        return self.author_name
    
    @property
    def display_email(self):
        """
        Get user email if registered
        احصل على بريد المستخدم إذا تم تسجيله
        """
        return self.linked_user.email if self.linked_user else None