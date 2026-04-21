from django.db import models
from citation.models import *
from journal.models import *
from keywords.models import *

class PublicationType(models.TextChoices):
    ARTICLE            = 'Article',           'Article'
    BOOK               = 'Book',              'Livre'
    CONFERENCE_PAPER   = 'Conference_Paper',  'Communication en conférence'
    REVIEW             = 'Review',            'Revue'

class Publication(models.Model):
    """
    Publication scientifique.
    Méthodes du diagramme : getCitationCount, getImpactFactor, getAltmetricScore
    """
    title            = models.CharField(max_length=1000)
    abstract         = models.TextField(blank=True)
    publication_year = models.IntegerField(null=True, blank=True)
    doi              = models.CharField(max_length=500, blank=True, unique=True, null=True)
    type             = models.CharField(max_length=20, choices=PublicationType.choices, default=PublicationType.ARTICLE)
    institution      = models.ForeignKey('institution.Institution', on_delete=models.SET_NULL, null=True, blank=True, related_name='publications')
    journal          = models.ForeignKey(Journal, on_delete=models.SET_NULL, null=True, blank=True, related_name='publications')
    keywords         = models.ManyToManyField(Keyword, blank=True, related_name='publications')
    citation_count    = models.IntegerField(default=0)
    altmetric_score   = models.FloatField(null=True, blank=True)  # Score Altmetric mis en cache
    is_validated      = models.BooleanField(default=True)  # Validation par un admin
    reseachers         = models.ManyToManyField('users.Researcher', blank=True, related_name='publications') # Co-auteurs (liés à des profils chercheurs)
    openalex_id = models.CharField(
    max_length=200,
    blank=True,
    null=True,
    unique=True,
    help_text="ID OpenAlex : https://openalex.org/W1234567890"
)

    class Meta:
        db_table = 'publications_publication'
    
    def __str__(self):
        return self.title

    def get_citation_count(self):
        """Retourne le nombre de citations reçues."""
        return Citation.objects.filter(cited_publication=self).count()
    def get_impact_factor(self) -> float:
        """Retourne l'impact factor du journal associé."""
        if self.journal and self.journal.impact_factor:
            return self.journal.impact_factor
        return 0.0
    def get_altmetric_score(self) -> float:
        """Retourne le score Altmetric (mis en cache)."""
        return self.altmetric_score if self.altmetric_score is not None else 0.0
    def validate(self):
        """Valide la publication (approuvée par un admin)."""
        self.is_validated = True
        self.save(update_fields=['is_validated'])
    def refresh_citation_count(self):
        self.citation_count = self.get_citation_count()
        self.save(update_fields=['citation_count'])
    