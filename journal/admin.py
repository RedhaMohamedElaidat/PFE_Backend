# journal/admin.py
from django.contrib import admin
from journal.models import Journal


@admin.register(Journal)
class JournalAdmin(admin.ModelAdmin):
    list_display  = ['id', 'name', 'issn', 'impact_factor']
    search_fields = ['name', 'issn']
    ordering      = ['-impact_factor']
    list_filter   = ['impact_factor']
    list_per_page = 25