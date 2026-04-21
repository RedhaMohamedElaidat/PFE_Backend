# keywords/admin.py
from django.contrib import admin
from keywords.models import Keyword


@admin.register(Keyword)
class KeywordAdmin(admin.ModelAdmin):
    list_display  = ['id', 'label']
    search_fields = ['label']
    ordering      = ['label']
    list_per_page = 50