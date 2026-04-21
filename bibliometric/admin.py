# bibliometric/admin.py - VERSION FINALE CORRIGÉE

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import BibliometrixAnalysis, ResearcherBibliometricCache, BibliometrixAnalysisHistory
import json


# ============================================================================
# 1. ADMIN POUR BIBLIOMETRIX ANALYSIS
# ============================================================================

@admin.register(BibliometrixAnalysis)
class BibliometrixAnalysisAdmin(admin.ModelAdmin):
    
    list_display = [
        'id',
        'analysis_type_colored',
        'created_at_formatted',
        'results_size',
        'records_count_display',
        'view_results_link'
    ]
    
    list_filter = ['analysis_type', 'created_at']
    search_fields = ['analysis_type', 'parameters__source_file']
    ordering = ['-created_at']
    
    readonly_fields = [
        'created_at',
        'updated_at',
        'results_preview',
        'results_raw',
        'statistics_summary'
    ]
    
    list_per_page = 50
    
    fieldsets = (
        ('Informations générales', {
            'fields': ('analysis_type', 'parameters', 'created_at', 'updated_at')
        }),
        ('Statistiques', {
            'fields': ('statistics_summary',),
            'classes': ('wide',)
        }),
        ('Aperçu des résultats', {
            'fields': ('results_preview',),
            'classes': ('wide',)
        }),
        ('Données brutes (JSON)', {
            'fields': ('results_raw',),
            'classes': ('collapse',)
        }),
    )
    
    # ========================================================================
    # MÉTHODES UTILITAIRES
    # ========================================================================
    
    def _safe_int(self, value, default=0):
        """Convertit une valeur en int, gère les listes de R"""
        if isinstance(value, list):
            return int(value[0]) if value else default
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return default
        return default
    
    def _safe_float(self, value, default=0.0):
        """Convertit une valeur en float, gère les listes de R"""
        if isinstance(value, list):
            return float(value[0]) if value else default
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return default
        return default
    
    def _safe_str(self, value, default="N/A"):
        """Convertit une valeur en string, gère les listes de R"""
        if isinstance(value, list):
            return str(value[0]) if value else default
        return str(value) if value is not None else default
    
    def _get_record_count(self, obj):
        """Retourne le nombre d'enregistrements selon le type"""
        results = obj.results
        
        if obj.analysis_type == 'all_authors':
            return len(results) if isinstance(results, list) else 0
        elif obj.analysis_type == 'all_keywords':
            if isinstance(results, dict):
                return len(results.get('all_keywords', []))
            return len(results) if isinstance(results, list) else 0
        elif obj.analysis_type == 'summary':
            return self._safe_int(results.get('total_publications', 0))
        elif obj.analysis_type == 'top_authors':
            return len(results) if isinstance(results, list) else 0
        elif obj.analysis_type == 'collaboration_network':
            return len(results) if isinstance(results, dict) else 0
        elif obj.analysis_type == 'author_publications':
            return len(results) if isinstance(results, dict) else 0
        elif obj.analysis_type == 'collaboration_edges':
            return len(results) if isinstance(results, list) else 0
        return 0
    
    # ========================================================================
    # MÉTHODES D'AFFICHAGE
    # ========================================================================
    
    def analysis_type_colored(self, obj):
        colors = {
            'summary': '#2ecc71',
            'top_authors': '#3498db',
            'thematic_clusters': '#9b59b6',
            'collaboration_network': '#e74c3c',
            'all_authors': '#27ae60',
            'all_keywords': '#8e44ad',
            'author_publications': '#2980b9',
            'collaboration_edges': '#d35400',
            'collaboration_network_complete': '#c0392b',
        }
        color = colors.get(obj.analysis_type, '#7f8c8d')
        
        type_names = {
            'summary': '📊 Résumé global',
            'top_authors': '🏆 Top auteurs',
            'thematic_clusters': '🎯 Clusters thématiques',
            'collaboration_network': '🌐 Réseau collaboration',
            'all_authors': '👥 Tous les auteurs',
            'all_keywords': '🔑 Tous les keywords',
            'author_publications': '📚 Publications auteurs',
            'collaboration_edges': '🔗 Arêtes collaboration',
            'collaboration_network_complete': '🌍 Réseau complet',
        }
        display_name = type_names.get(obj.analysis_type, obj.analysis_type)
        
        return format_html(
            '<span style="background-color: {}; padding: 5px 12px; border-radius: 20px; color: white; font-size: 12px; font-weight: bold;">{}</span>',
            color, display_name
        )
    analysis_type_colored.short_description = "Type d'analyse"
    
    def created_at_formatted(self, obj):
        return obj.created_at.strftime("%d/%m/%Y %H:%M:%S")
    created_at_formatted.short_description = "Date de création"
    
    def results_size(self, obj):
        size_bytes = len(json.dumps(obj.results))
        size_kb = size_bytes / 1024
        if size_kb < 1024:
            return f"📄 {size_kb:.1f} KB"
        return f"📦 {size_kb/1024:.1f} MB"
    results_size.short_description = "Taille"
    
    def records_count_display(self, obj):
        count = self._get_record_count(obj)
        if count > 0:
            return mark_safe(f'<span style="background-color: #e8f4fd; padding: 3px 10px; border-radius: 15px; font-size: 11px;">📊 {count:,}</span>')
        return "-"
    records_count_display.short_description = "Enregistrements"
    
    # ========================================================================
    # STATISTIQUES RÉSUMÉES
    # ========================================================================
    
    def statistics_summary(self, obj):
        results = obj.results
        
        if obj.analysis_type == 'summary':
            pubs = self._safe_int(results.get('total_publications', 0))
            cites = self._safe_int(results.get('total_citations', 0))
            avg = self._safe_float(results.get('avg_citations', 0))
            
            html = '<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px; color: white;">'
            html += '<h3 style="margin: 0 0 15px 0;">📈 Statistiques globales</h3>'
            html += '<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px;">'
            html += f'<div style="background: rgba(255,255,255,0.2); padding: 15px; border-radius: 8px;"><div style="font-size: 28px; font-weight: bold;">{pubs:,}</div><div>Publications</div></div>'
            html += f'<div style="background: rgba(255,255,255,0.2); padding: 15px; border-radius: 8px;"><div style="font-size: 28px; font-weight: bold;">{cites:,}</div><div>Citations</div></div>'
            html += f'<div style="background: rgba(255,255,255,0.2); padding: 15px; border-radius: 8px;"><div style="font-size: 28px; font-weight: bold;">{avg:.1f}</div><div>Moyenne citations</div></div>'
            html += '</div></div>'
            return mark_safe(html)
        
        elif obj.analysis_type == 'all_authors':
            total_authors = len(results) if isinstance(results, list) else 0
            html = '<div style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); padding: 20px; border-radius: 10px; color: white;">'
            html += '<h3 style="margin: 0 0 15px 0;">👥 Auteurs</h3>'
            html += f'<div style="background: rgba(255,255,255,0.2); padding: 15px; border-radius: 8px;"><div style="font-size: 28px; font-weight: bold;">{total_authors:,}</div><div>Auteurs uniques</div></div>'
            html += '</div>'
            return mark_safe(html)
        
        elif obj.analysis_type == 'all_keywords':
            keywords = results.get('all_keywords', []) if isinstance(results, dict) else results
            total_keywords = len(keywords)
            html = '<div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); padding: 20px; border-radius: 10px; color: white;">'
            html += '<h3 style="margin: 0 0 15px 0;">🔑 Mots-clés</h3>'
            html += f'<div style="background: rgba(255,255,255,0.2); padding: 15px; border-radius: 8px;"><div style="font-size: 28px; font-weight: bold;">{total_keywords:,}</div><div>Keywords uniques</div></div>'
            html += '</div>'
            return mark_safe(html)
        
        return mark_safe('<div style="padding: 10px; background: #f8f9fa; border-radius: 5px;">Sélectionnez un type d\'analyse</div>')
    statistics_summary.short_description = "📊 Résumé statistique"
    
    # ========================================================================
    # APERÇU DES RÉSULTATS
    # ========================================================================
    
    def results_preview(self, obj):
        """Aperçu formaté complet des résultats - CORRIGÉ"""
        results = obj.results
        
        # ===== SUMMARY =====
        if obj.analysis_type == 'summary':
            pubs = self._safe_int(results.get("total_publications", 0))
            cites = self._safe_int(results.get("total_citations", 0))
            avg = self._safe_float(results.get("avg_citations", 0))
            
            years = results.get("years_range", {})
            min_year = self._safe_int(years.get("min", "N/A"))
            max_year = self._safe_int(years.get("max", "N/A"))
            yearly = results.get("yearly_output", {})
            
            html = '<div style="background: #f8f9fa; padding: 20px; border-radius: 10px;">'
            html += '<div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 25px;">'
            html += f'<div style="background: white; padding: 15px; border-radius: 8px; text-align: center;"><div style="font-size: 32px; font-weight: bold; color: #2ecc71;">{pubs:,}</div><div>Publications</div></div>'
            html += f'<div style="background: white; padding: 15px; border-radius: 8px; text-align: center;"><div style="font-size: 32px; font-weight: bold; color: #3498db;">{cites:,}</div><div>Citations</div></div>'
            html += f'<div style="background: white; padding: 15px; border-radius: 8px; text-align: center;"><div style="font-size: 32px; font-weight: bold; color: #9b59b6;">{avg:.1f}</div><div>Moyenne citations</div></div>'
            html += f'<div style="background: white; padding: 15px; border-radius: 8px; text-align: center;"><div style="font-size: 32px; font-weight: bold; color: #e74c3c;">{min_year}-{max_year}</div><div>Période</div></div>'
            html += '</div>'
            
            # Graphique production annuelle - CORRIGÉ
            if yearly and isinstance(yearly, dict):
                # Convertir toutes les valeurs en int
                yearly_clean = {}
                for year, count in yearly.items():
                    yearly_clean[year] = self._safe_int(count)
                
                if yearly_clean:
                    html += '<div style="background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;"><h4>📅 Production annuelle</h4><div style="display: flex; align-items: flex-end; gap: 5px; min-height: 200px;">'
                    max_val = max(yearly_clean.values()) if yearly_clean else 1
                    
                    for year in sorted(yearly_clean.keys()):
                        count = yearly_clean[year]
                        height = (count / max_val) * 150 if max_val > 0 else 0
                        html += f'<div style="flex:1;text-align:center;"><div style="background:#3498db;height:{height}px;border-radius:4px 4px 0 0;"></div><div style="font-size:11px;margin-top:8px;">{year}</div><div style="font-size:10px;color:#666;">{count}</div></div>'
                    html += '</div></div>'
            
            # Top journaux
            top_journals = results.get('top_journals', [])
            if top_journals and isinstance(top_journals, list):
                html += '<div style="background: white; padding: 20px; border-radius: 8px;"><h4>📰 Top 20 journaux</h4><table style="width:100%; border-collapse: collapse;">'
                for j in top_journals[:20]:
                    if isinstance(j, dict):
                        journal = self._safe_str(j.get("journal", "N/A"))
                        count = self._safe_int(j.get("count", 0))
                        html += f'<tr style="border-bottom: 1px solid #eee;"><td style="padding: 8px;">{journal}</td><td style="padding: 8px; text-align: right;"><strong>{count}</strong></td></tr>'
                html += '</table></div>'
            html += '</div>'
            return mark_safe(html)
        
        # ===== ALL AUTHORS =====
        elif obj.analysis_type == 'all_authors':
            total_authors = len(results) if isinstance(results, list) else 0
            html = '<div style="background: #f8f9fa; padding: 20px; border-radius: 10px;">'
            html += f'<h3>👥 Tous les auteurs</h3><p><strong>{total_authors:,}</strong> auteurs uniques</p>'
            html += '<div style="background: white; border-radius: 8px; overflow-x: auto;"><table style="width:100%; border-collapse: collapse;">'
            html += '<thead><tr style="background:#2c3e50;color:white"><th style="padding: 10px;">Rang</th><th style="padding: 10px; text-align: left;">Auteur</th><th style="padding: 10px;">Publications</th></tr></thead><tbody>'
            
            for author in results[:100]:
                if isinstance(author, dict):
                    rank = self._safe_int(author.get("rank", "-"))
                    name = self._safe_str(author.get("name", "N/A"))
                    pubs = self._safe_int(author.get("publications", 0))
                    html += f'<tr style="border-bottom: 1px solid #eee;"><td style="padding: 8px; text-align: center;">{rank}</td><td style="padding: 8px;"><strong>{name}</strong></td><td style="padding: 8px; text-align: right;">{pubs:,}</td></tr>'
            
            html += '</tbody></table>'
            if total_authors > 100:
                html += f'<div style="padding: 15px; text-align: center; background: #e9ecef;">... et {total_authors - 100} autres auteurs</div>'
            html += '</div></div>'
            return mark_safe(html)
        
        # ===== ALL KEYWORDS =====
        elif obj.analysis_type == 'all_keywords':
            keywords = results.get('all_keywords', []) if isinstance(results, dict) else results
            total_keywords = len(keywords)
            
            html = '<div style="background: #f8f9fa; padding: 20px; border-radius: 10px;">'
            html += f'<h3>🔑 Tous les mots-clés</h3><p><strong>{total_keywords:,}</strong> keywords uniques</p>'
            
            # Nuage de tags
            html += '<div style="background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;"><h4>☁️ Nuage des top 50 keywords</h4><div style="display: flex; flex-wrap: wrap; gap: 10px;">'
            for kw in keywords[:50]:
                if isinstance(kw, dict):
                    keyword = self._safe_str(kw.get("keyword", "N/A"))
                    freq = self._safe_int(kw.get("frequency", 0))
                    size = max(12, min(28, 12 + (freq // 50)))
                    html += f'<span style="background:#e3f2fd;padding:5px 15px;border-radius:20px;font-size:{size}px;color:#1565c0;">{keyword} ({freq})</span>'
            html += '</div></div>'
            
            # Tableau
            html += '<div style="background: white; border-radius: 8px; overflow-x: auto;"><table style="width:100%; border-collapse: collapse;">'
            html += '<thead><tr style="background:#2c3e50;color:white"><th style="padding: 10px;">Rang</th><th style="padding: 10px; text-align: left;">Keyword</th><th style="padding: 10px;">Fréquence</th></tr></thead><tbody>'
            
            for kw in keywords[:100]:
                if isinstance(kw, dict):
                    rank = self._safe_int(kw.get("rank", "-"))
                    keyword = self._safe_str(kw.get("keyword", "N/A"))
                    freq = self._safe_int(kw.get("frequency", 0))
                    html += f'<tr style="border-bottom: 1px solid #eee;"><td style="padding: 8px; text-align: center;">{rank}</td><td style="padding: 8px;"><strong>{keyword}</strong></td><td style="padding: 8px; text-align: right;">{freq:,}</td></tr>'
            
            html += '</tbody></table></div></div>'
            return mark_safe(html)
        
        # ===== TOP AUTHORS =====
        elif obj.analysis_type == 'top_authors':
            html = '<div style="background: #f8f9fa; padding: 20px; border-radius: 10px;"><h3>🏆 Top auteurs</h3>'
            html += '<div style="background: white; border-radius: 8px;"><table style="width:100%; border-collapse: collapse;">'
            html += '<thead><tr style="background:#2c3e50;color:white"><th style="padding: 10px;">Rang</th><th style="padding: 10px; text-align: left;">Auteur</th><th style="padding: 10px;">Publications</th></tr></thead><tbody>'
            
            for author in results[:50]:
                if isinstance(author, dict):
                    rank = self._safe_int(author.get("rank", "-"))
                    name = self._safe_str(author.get("name", "N/A"))
                    pubs = self._safe_int(author.get("publications", 0))
                    html += f'<tr style="border-bottom: 1px solid #eee;"><td style="padding: 8px; text-align: center;">{rank}</td><td style="padding: 8px;"><strong>{name}</strong></td><td style="padding: 8px; text-align: right;">{pubs:,}</td></tr>'
            
            html += '</tbody></table></div></div>'
            return mark_safe(html)
        
        # ===== COLLABORATION NETWORK COMPLETE =====
        elif obj.analysis_type == 'collaboration_network_complete':
            html = '<div style="background: #f8f9fa; padding: 20px; border-radius: 10px;"><h3>🌍 Réseau de collaboration complet</h3>'
            if isinstance(results, dict):
                # Trier par nombre de publications
                sorted_authors = sorted(results.items(), key=lambda x: self._safe_int(x[1].get('total_publications', 0)), reverse=True)
                html += '<div style="background: white; border-radius: 8px;"><table style="width:100%; border-collapse: collapse;">'
                html += '<thead><tr style="background:#2c3e50;color:white"><th style="padding: 10px;">Rang</th><th style="padding: 10px; text-align: left;">Auteur</th><th style="padding: 10px;">Publications</th><th style="padding: 10px;">Collaborateurs</th></tr></thead><tbody>'
                
                for i, (author, data) in enumerate(sorted_authors[:50], 1):
                    pubs = self._safe_int(data.get('total_publications', 0))
                    collabs = len(data.get('all_collaborators', []))
                    html += f'<tr style="border-bottom: 1px solid #eee;"><td style="padding: 8px; text-align: center;">{i}</td><td style="padding: 8px;"><strong>{author}</strong></td><td style="padding: 8px; text-align: right;">{pubs:,}</td><td style="padding: 8px; text-align: center;">{collabs}</td></tr>'
                
                html += '</tbody></table></div>'
            html += '</div>'
            return mark_safe(html)
        
        # ===== DEFAULT =====
        else:
            preview = json.dumps(results, indent=2)[:2000]
            return mark_safe(f'<pre style="background:#2c3e50;color:#00ff9d;padding:15px;border-radius:8px;overflow-x:auto;max-height:500px;">{preview}</pre>')
    
    def results_raw(self, obj):
        return mark_safe(f'<pre style="background:#1a1a2e;color:#00ff9d;padding:20px;border-radius:10px;overflow-x:auto;max-height:600px;font-size:12px;">{json.dumps(obj.results, indent=2)[:10000]}</pre>')
    results_raw.short_description = "📄 Données brutes JSON"
    
    def view_results_link(self, obj):
        url = reverse('admin:bibliometric_bibliometrixanalysis_change', args=[obj.id])
        return format_html('<a href="{}" style="background:#3498db;color:white;padding:5px 12px;border-radius:5px;text-decoration:none;">🔍 Voir détails</a>', url)
    view_results_link.short_description = "Actions"
    
    actions = ['export_as_json']
    
    def export_as_json(self, request, queryset):
        from django.http import HttpResponse
        data = [{'id': obj.id, 'analysis_type': obj.analysis_type, 'parameters': obj.parameters, 'results': obj.results, 'created_at': obj.created_at.isoformat()} for obj in queryset]
        response = HttpResponse(json.dumps(data, indent=2), content_type='application/json')
        response['Content-Disposition'] = 'attachment; filename="bibliometrix_analyses.json"'
        return response
    export_as_json.short_description = "📥 Exporter en JSON"


# ============================================================================
# 2. ADMIN POUR CACHE CHERCHEUR
# ============================================================================

@admin.register(ResearcherBibliometricCache)
class ResearcherBibliometricCacheAdmin(admin.ModelAdmin):
    list_display = ['id', 'researcher_link', 'h_index_badge', 'total_papers', 'total_citations', 'avg_citations', 'years_active', 'updated_at_formatted', 'refresh_link']
    list_filter = ['updated_at']
    search_fields = ['researcher__user__username', 'researcher__user__first_name', 'researcher__user__last_name']
    ordering = ['-h_index', '-total_papers']
    readonly_fields = ['created_at', 'updated_at', 'researcher_details', 'yearly_output_display', 'top_keywords_display', 'full_details']
    list_per_page = 30
    
    fieldsets = (
        ('Chercheur', {'fields': ('researcher', 'researcher_details')}),
        ('Indicateurs principaux', {'fields': ('h_index', 'g_index', 'm_index')}),
        ('Production', {'fields': ('total_papers', 'total_citations', 'avg_citations')}),
        ('Période d\'activité', {'fields': ('first_publication_year', 'last_publication_year', 'years_active')}),
        ('Analyses détaillées', {'fields': ('yearly_output_display', 'top_keywords_display', 'full_details'), 'classes': ('wide', 'collapse')}),
        ('Métadonnées', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
    
    def researcher_link(self, obj):
        url = reverse('admin:users_researcher_change', args=[obj.researcher.id])
        return format_html('<a href="{}" style="font-weight: bold;">{}</a>', url, obj.researcher.user.username)
    researcher_link.short_description = "Chercheur"
    
    def researcher_details(self, obj):
        user = obj.researcher.user
        return format_html(
            '<div style="background:#f8f9fa;padding:10px;border-radius:5px;">'
            '<p><strong>Nom complet:</strong> {} {}</p>'
            '<p><strong>Email:</strong> {}</p>'
            '<p><strong>ORCID:</strong> {}</p>'
            '<p><strong>Domaine:</strong> {}</p></div>',
            user.first_name or '', user.last_name or '', user.email or 'N/A', 
            obj.researcher.orcid or 'N/A', obj.researcher.research_field or 'N/A'
        )
    
    def h_index_badge(self, obj):
        color = '#27ae60' if obj.h_index >= 40 else '#f39c12' if obj.h_index >= 20 else '#3498db' if obj.h_index >= 10 else '#95a5a6'
        return format_html('<span style="background-color:{};padding:5px 10px;border-radius:20px;color:white;font-weight:bold;">{}</span>', color, obj.h_index)
    h_index_badge.short_description = "H-index"
    
    def updated_at_formatted(self, obj):
        from django.utils import timezone
        from datetime import timedelta
        diff = timezone.now() - obj.updated_at
        if diff < timedelta(hours=1):
            return format_html('<span style="color:#27ae60;">🟢 À jour</span>')
        elif diff < timedelta(days=1):
            return format_html('<span style="color:#f39c12;">🟡 {} heures</span>', int(diff.seconds / 3600))
        return format_html('<span style="color:#e74c3c;">🔴 {} jours</span>', diff.days)
    updated_at_formatted.short_description = "État"
    
    def refresh_link(self, obj):
        url = reverse('admin:users_researcher_change', args=[obj.researcher.id])
        return format_html('<a href="{}" style="background:#3498db;color:white;padding:3px 8px;border-radius:3px;text-decoration:none;">🔄 Mettre à jour</a>', url)
    refresh_link.short_description = "Action"
    
    def yearly_output_display(self, obj):
        yearly = obj.yearly_output
        if not yearly:
            return "Aucune donnée"
        
        # Nettoyer les données
        yearly_clean = {}
        for year, count in yearly.items():
            yearly_clean[year] = self._safe_int(count) if hasattr(self, '_safe_int') else int(count[0]) if isinstance(count, list) else int(count)
        
        max_val = max(yearly_clean.values()) if yearly_clean else 1
        html = '<div style="background:#f8f9fa;padding:15px;border-radius:5px;"><h4>📅 Production annuelle</h4><div style="display:flex;align-items:flex-end;gap:2px;height:150px;">'
        for year in sorted(yearly_clean.keys()):
            count = yearly_clean[year]
            height = (count / max_val) * 120 if max_val > 0 else 0
            html += f'<div style="flex:1;text-align:center;"><div style="background:#3498db;height:{height}px;border-radius:3px 3px 0 0;"></div><div style="font-size:10px;margin-top:5px;">{year}</div><div style="font-size:9px;color:#666;">{count}</div></div>'
        html += '</div></div>'
        return format_html(html)
    yearly_output_display.short_description = "Production annuelle"
    
    def top_keywords_display(self, obj):
        keywords = obj.top_keywords
        if not keywords:
            return "Aucun keyword"
        html = '<div style="background:#f8f9fa;padding:15px;border-radius:5px;"><h4>🔑 Top keywords</h4><div style="display:flex;flex-wrap:wrap;gap:8px;">'
        for kw in keywords[:15]:
            if isinstance(kw, dict):
                keyword = kw.get('keyword', 'N/A')
                count = kw.get('count', '')
            else:
                keyword = str(kw)
                count = ''
            html += f'<span style="background:#e9ecef;padding:5px 12px;border-radius:20px;font-size:12px;">{keyword} <span style="color:#666;">({count})</span></span>'
        html += '</div></div>'
        return format_html(html)
    top_keywords_display.short_description = "Top keywords"
    
    def full_details(self, obj):
        return format_html(
            '<pre style="background:#2c3e50;color:#ecf0f1;padding:15px;border-radius:5px;overflow-x:auto;max-height:300px;">{}</pre>',
            json.dumps({
                'h_index': obj.h_index, 'g_index': obj.g_index, 'm_index': obj.m_index,
                'total_papers': obj.total_papers, 'total_citations': obj.total_citations,
                'avg_citations': obj.avg_citations, 'first_year': obj.first_publication_year,
                'last_year': obj.last_publication_year, 'years_active': obj.years_active,
                'yearly_output': obj.yearly_output, 'top_keywords': obj.top_keywords[:10]
            }, indent=2)
        )
    
    actions = ['export_selected_caches']
    
    def export_selected_caches(self, request, queryset):
        import csv
        from django.http import HttpResponse
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="bibliometric_caches.csv"'
        writer = csv.writer(response)
        writer.writerow(['ID', 'Chercheur', 'H-index', 'G-index', 'Publications', 'Citations', 'Moyenne citations', 'Première année', 'Dernière année', 'Années actives', 'Dernière mise à jour'])
        for cache in queryset:
            writer.writerow([cache.id, cache.researcher.user.username, cache.h_index, cache.g_index, 
                           cache.total_papers, cache.total_citations, cache.avg_citations, 
                           cache.first_publication_year or '', cache.last_publication_year or '', 
                           cache.years_active, cache.updated_at.strftime('%Y-%m-%d %H:%M:%S')])
        return response
    export_selected_caches.short_description = "📥 Exporter en CSV"


# ============================================================================
# 3. ADMIN POUR HISTORIQUE
# ============================================================================

@admin.register(BibliometrixAnalysisHistory)
class BibliometrixAnalysisHistoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'researcher_link', 'h_index', 'total_papers', 'total_citations', 'analysis_date']
    list_filter = ['analysis_date']
    search_fields = ['researcher__user__username']
    ordering = ['-analysis_date', '-h_index']
    
    def researcher_link(self, obj):
        url = reverse('admin:users_researcher_change', args=[obj.researcher.id])
        return format_html('<a href="{}">{}</a>', url, obj.researcher.user.username)
    researcher_link.short_description = "Chercheur"