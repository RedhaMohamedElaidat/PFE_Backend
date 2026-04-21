from django.db import models

class DataSource(models.TextChoices):
    OPENALEX   = 'OpenAlex',   'OpenAlex'
    SCOPUS     = 'Scopus',     'Scopus'
    WOS        = 'Wos',        'Web of Science'
    CROSSREF   = 'Crossref',   'Crossref'
    DIMENSIONS = 'Dimensions', 'Dimensions'

class Citation(models.Model):
    citing_publication = models.ForeignKey('publication.Publication', on_delete=models.CASCADE, related_name='citations_made')
    cited_publication  = models.ForeignKey('publication.Publication', on_delete=models.CASCADE, related_name='citations_received')
    source             = models.CharField(max_length=20, choices=DataSource.choices, blank=True)
    external_id        = models.CharField(max_length=255, blank=True)  # ID de la citation dans la source externe
    citation_date      = models.DateField(null=True, blank=True)
    openalex_id        = models.CharField(max_length=200, blank=True, null=True, unique=True,db_index=True, help_text="ID OpenAlex de la citation : https://openalex.org/C1234567890")
    class Meta:
        db_table = 'citations'
        verbose_name = 'Citation'
        verbose_name_plural = 'Citations'
        unique_together = ('citing_publication', 'cited_publication')
    def __str__(self):
        return f"Citation: {self.citing_publication.title} -> {self.cited_publication.title}"
    

