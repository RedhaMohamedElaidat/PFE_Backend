# users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from users.models import InstitutionDirector, User, Admin, Researcher, LabManager, TeamLeader


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display   = ['user_id', 'username', 'email', 'first_name',
                      'last_name', 'is_active', 'is_staff', 'created_at']
    search_fields  = ['username', 'email', 'first_name', 'last_name']
    list_filter    = ['is_active', 'is_staff']
    ordering       = ['-created_at']
    list_per_page  = 25
    fieldsets      = BaseUserAdmin.fieldsets + (
        ('Informations supplémentaires', {'fields': ('created_at', 'updated_at')}),
    )
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Admin)
class AdminAdmin(admin.ModelAdmin):
    list_display  = ['user', 'role']
    list_filter   = ['role']
    search_fields = ['user__username', 'user__email']

from django.contrib import admin
from django.contrib import messages
from .models import User, Researcher
from data_pipeline.link_researcher_publications import link_by_name, link_by_orcid

@admin.register(Researcher)
class ResearcherAdmin(admin.ModelAdmin):
    list_display = ['user', 'orcid', 'h_index', 'research_field', 'publications_count']
    search_fields = ['user__username', 'orcid', 'user__first_name', 'user__last_name']
    
    def publications_count(self, obj):
        return obj.publications.count()
    publications_count.short_description = 'Publications'
    
    def save_model(self, request, obj, form, change):
        # Sauvegarder d'abord
        super().save_model(request, obj, form, change)
        
        # Si c'est un nouveau chercheur
        if not change:
            # Essayer de lier par ORCID d'abord
            if obj.orcid:
                stats = link_by_orcid(obj.user, obj.orcid)
                messages.success(
                    request, 
                    f"✅ {stats['publications_linked']} publications liées via ORCID"
                )
            else:
                # Sinon lier par nom
                stats = link_by_name(obj.user)
                messages.success(
                    request, 
                    f"✅ {stats['publications_linked']} publications liées via le nom '{obj.user.get_full_name()}'"
                )

@admin.register(LabManager)
class LabManagerAdmin(admin.ModelAdmin):
    list_display  = ['user', 'laboratory', 'start_date', 'end_date']
    search_fields = ['user__username', 'laboratory__name']
    list_filter   = ['laboratory']


@admin.register(TeamLeader)
class TeamLeaderAdmin(admin.ModelAdmin):
    list_display  = ['user', 'team', 'start_date', 'end_date']
    search_fields = ['user__username', 'team__name']
    list_filter   = ['team']

@admin.register(InstitutionDirector)
class InstitutionDirectorAdmin(admin.ModelAdmin):
    list_display  = ['user', 'institution', 'start_date', 'end_date']
    search_fields = ['user__username', 'institution__name']
    list_filter   = ['institution']