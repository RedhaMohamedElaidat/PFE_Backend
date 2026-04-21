# coAuthor/admin.py - VERSION CORRIGÉE

from django.contrib import admin
from coAuthor.models import CoAuthor


@admin.register(CoAuthor)
class CoAuthorAdmin(admin.ModelAdmin):
    list_display = [
        'ID', 
        'display_author_name',      # Changé: utilise le champ direct
        'publication_short',
        'get_contribution_type_display', 
        'author_order',
        'affiliation_at_time',
        'linked_user_display',      # Ajouté: voir si lié à un user
    ]
    
    search_fields = [
        'author_name',              # Changé: champ direct au lieu de author__username
        'author_orcid',             # Ajouté: chercher par ORCID
        'openalex_id',              # Ajouté: chercher par OpenAlex ID
        'publication__title',       # Gardé: chercher dans le titre de la publication
        'linked_user__username',    # Ajouté: chercher par username du user lié
        'linked_user__email',       # Ajouté: chercher par email du user lié
        'affiliation_at_time',      # Ajouté: chercher par affiliation
    ]
    
    list_filter = [
        'contribution_type',
        'author_order',
    ]
    
    ordering = ['publication', 'author_order']
    list_per_page = 25
    list_select_related = ['publication', 'linked_user']  # Optimisation
    
    readonly_fields = ['ID', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Publication Information', {
            'fields': ('publication', 'author_name', 'author_orcid', 'openalex_id')
        }),
        ('Authorship Details', {
            'fields': ('author_order', 'contribution_type', 'affiliation_at_time')
        }),
        ('User Link (Auto via ORCID)', {
            'fields': ('linked_user',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('ID', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    # ──────────────────────────────────────────────────────────────────────────
    # METHODES D'AFFICHAGE
    # ──────────────────────────────────────────────────────────────────────────
    
    def display_author_name(self, obj):
        """Affiche le nom de l'auteur avec un badge si c'est un user enregistré"""
        if obj.linked_user:
            return f"👤 {obj.author_name} (✓ {obj.linked_user.username})"
        return f"📝 {obj.author_name}"
    display_author_name.short_description = 'Auteur'
    display_author_name.admin_order_field = 'author_name'
    
    def publication_short(self, obj):
        """Affiche un aperçu du titre de la publication"""
        title = obj.publication.title[:50]
        if obj.publication.publication_year:
            return f"{title}... ({obj.publication.publication_year})"
        return f"{title}..."
    publication_short.short_description = 'Publication'
    publication_short.admin_order_field = 'publication__title'
    
    def linked_user_display(self, obj):
        """Affiche le user lié s'il existe"""
        if obj.linked_user:
            return obj.linked_user.username
        return "❌ Non lié"
    linked_user_display.short_description = 'Utilisateur lié'
    linked_user_display.admin_order_field = 'linked_user__username'
    
    # ──────────────────────────────────────────────────────────────────────────
    # ACTIONS PERSONNALISÉES
    # ──────────────────────────────────────────────────────────────────────────
    
    actions = ['link_to_existing_users']
    
    def link_to_existing_users(self, request, queryset):
        """Action admin pour lier manuellement des coauthors à des users existants"""
        from users.models import Researcher
        from django.contrib import messages
        
        linked_count = 0
        not_found_count = 0
        
        for coauthor in queryset:
            if coauthor.author_orcid and not coauthor.linked_user:
                # Chercher un researcher avec cet ORCID
                try:
                    researcher = Researcher.objects.get(orcid=coauthor.author_orcid)
                    coauthor.linked_user = researcher.user
                    coauthor.save()
                    linked_count += 1
                except Researcher.DoesNotExist:
                    not_found_count += 1
        
        messages.success(
            request, 
            f"{linked_count} co-auteurs liés à des utilisateurs existants. "
            f"{not_found_count} ORCID non trouvés."
        )
    
    link_to_existing_users.short_description = "Lier aux utilisateurs existants (par ORCID)"
    
    # ──────────────────────────────────────────────────────────────────────────
    # SURCHARGES PERSONNALISÉES
    # ──────────────────────────────────────────────────────────────────────────
    
    def get_queryset(self, request):
        """Optimiser les requêtes avec select_related"""
        return super().get_queryset(request).select_related(
            'publication', 'linked_user'
        )
    
    def save_model(self, request, obj, form, change):
        """Log quand un coauthor est modifié"""
        if change:
            self.message_user(request, f"Co-auteur '{obj.author_name}' mis à jour")
        else:
            self.message_user(request, f"Co-auteur '{obj.author_name}' créé")
        super().save_model(request, obj, form, change)