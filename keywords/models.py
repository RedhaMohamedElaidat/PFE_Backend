from django.db import models

# Create your models here.
class Keyword(models.Model):
    id = models.AutoField(primary_key=True)
    label = models.CharField(max_length=200, unique=True)

    class Meta:
        db_table = 'publications_keyword'

    def __str__(self):
        return self.label