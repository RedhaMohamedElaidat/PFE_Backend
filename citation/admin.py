# citation/admin.py
from django.contrib import admin
from citation.models import Citation


@admin.register(Citation)
class CitationAdmin(admin.ModelAdmin):
    list_display  = [
        'id',
        'citing_short', 'cited_short',
        'source', 'citation_date', 'external_id',
    ]
    search_fields = [
        'citing_publication__title',
        'cited_publication__title',
        'external_id',
    ]
    list_filter   = ['source', 'citation_date']
    ordering      = ['-citation_date']
    list_per_page = 25

    def citing_short(self, obj):
        return obj.citing_publication.title[:40]
    citing_short.short_description = 'Citante'

    def cited_short(self, obj):
        return obj.cited_publication.title[:40]
    cited_short.short_description = 'Citée'