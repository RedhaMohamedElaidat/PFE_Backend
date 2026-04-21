from django.db import models

# Create your models here.
class Journal(models.Model):
    id            = models.AutoField(primary_key=True)
    name          = models.CharField(max_length=500)
    impact_factor = models.FloatField(null=True, blank=True)
    issn          = models.CharField(max_length=20, blank=True, unique=True, null=True)

    class Meta:
        db_table = 'publications_journal'

    def __str__(self):
        return self.name