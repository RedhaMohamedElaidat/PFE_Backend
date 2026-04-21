from laboratory.models import Laboratory
from django.contrib import admin

@admin.register(Laboratory)
class LaboratoryAdmin(admin.ModelAdmin):
        list_display  = ['ID', 'name', 'institution', 'website',
                        'current_manager', 'get_team_count']
        search_fields = ['name', 'description']
        list_filter   = ['institution']
        ordering      = ['name']
        list_per_page = 25

        

        def get_team_count(self, obj):
            return obj.teams.count()
        get_team_count.short_description = 'Équipes'

