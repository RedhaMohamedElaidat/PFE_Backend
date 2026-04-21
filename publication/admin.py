# publication/admin.py
from django.contrib import admin
from publication.models import Publication

@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    # Liste simple sans champs problématiques
    list_display = ('id', 'title', 'publication_year', 'type', 'citation_count')
    
    ordering = ('-publication_year',)
    
    search_fields = ('title', 'abstract', 'doi')
    
    list_filter = ('publication_year', 'type')
    
    # Enlever created_at et updated_at des readonly_fields
    readonly_fields = ('citation_count',)  # juste citation_count si vous voulez
    
    fieldsets = (
        ('Informations principales', {
            'fields': ('title', 'abstract', 'doi', 'type')
        }),
        ('Métadonnées', {
            'fields': ('publication_year', 'journal', 'institution')
        }),
        ('Statistiques', {
            'fields': ('citation_count', 'altmetric_score')
        }),
    )