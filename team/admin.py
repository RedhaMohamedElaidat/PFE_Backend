# team/admin.py
from django.contrib import admin
from team.models import Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display   = ['ID', 'name', 'laboratory', 'get_member_count', 'get_current_leader']
    search_fields  = ['name', 'description']
    list_filter    = ['laboratory']
    ordering       = ['name']
    filter_horizontal = ['members']   # ← widget pratique pour M2M dans l'admin
    list_per_page  = 25

    def get_member_count(self, obj):
        return obj.members.count()
    get_member_count.short_description = 'Membres'

    def get_current_leader(self, obj):
        leader = obj.current_leader
        return leader.get_full_name() if leader else '—'
    get_current_leader.short_description = 'Chef d\'équipe'