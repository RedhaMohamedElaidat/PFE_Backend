from django.db import models
from django.utils import timezone
from laboratory.models import Laboratory
from publication.models import Publication
from users.models import Researcher
from django.db.models import Sum, Avg, Count

# ─────────────────────────────────────────
# TYPES
# ─────────────────────────────────────────
class TypeInstitution(models.TextChoices):
    UNIVERSITY = 'University', 'Université'
    RESEARCH_CENTER = 'Research_Center', 'Centre de Recherche'
    UNIVERSITY_CENTER = 'University_Center', 'Centre Universitaire'
    ECOLE = 'Ecole', 'Ecole'


# ─────────────────────────────────────────
# LOCATION (SIMPLIFIÉ)
# Country → Wilaya → Ville
# ─────────────────────────────────────────
class Country(models.Model):
    name = models.CharField(max_length=200, unique=True)

    class Meta:
        db_table = 'country'
        ordering = ['name']

    def __str__(self):
        return self.name


class Wilaya(models.Model):
    name = models.CharField(max_length=200)
    country = models.ForeignKey(
        Country,
        on_delete=models.CASCADE,
        related_name='wilayas'
    )

    class Meta:
        db_table = 'wilaya'
        ordering = ['name']
        unique_together = ['name', 'country']  # 🔥 important

    def __str__(self):
        return f"{self.name} ({self.country.name})"


class Ville(models.Model):
    name = models.CharField(max_length=200)
    wilaya = models.ForeignKey(
        Wilaya,
        on_delete=models.CASCADE,
        related_name='villes'
    )

    class Meta:
        db_table = 'ville'
        ordering = ['name']
        unique_together = ['name', 'wilaya']  # 🔥 important

    def __str__(self):
        return f"{self.name} ({self.wilaya.name})"


# ─────────────────────────────────────────
# INSTITUTION
# ─────────────────────────────────────────
class Institution(models.Model):
    id = models.AutoField(primary_key=True)  # 🔥 id explicite
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=20, choices=TypeInstitution.choices)
    website = models.URLField(blank=True)

    ville = models.ForeignKey(
        Ville,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='institutions'
    )

    class Meta:
        db_table = 'institution'
        ordering = ['name']

    def __str__(self):
        return self.name
    def get_total_publications(self):
        """Nombre total de publications de tous les laboratoires de l'institution"""
        from publication.models import Publication
        from coAuthor.models import CoAuthor
        
        # Récupérer tous les chercheurs des laboratoires de l'institution
        lab_ids = self.laboratories.values_list('ID', flat=True)
        
        if not lab_ids:
            return 0
            
        # Publications via les chercheurs des laboratoires
        publications = Publication.objects.filter(
            coauthors__linked_user__teams__laboratory__in=lab_ids,
            is_validated=True
        ).distinct()
        
        return publications.count()
    
    def get_total_citations(self):
        """Total des citations de tous les laboratoires"""
        from publication.models import Publication
        from django.db.models import Sum
        
        lab_ids = self.laboratories.values_list('ID', flat=True)
        
        if not lab_ids:
            return 0
            
        total = Publication.objects.filter(
            coauthors__linked_user__teams__laboratory__in=lab_ids,
            is_validated=True
        ).aggregate(total=Sum('citation_count'))['total'] or 0
        
        return total
    
    def get_total_collaborations(self):
        """Nombre total de collaborations uniques"""
        from coAuthor.models import CoAuthor
        
        lab_ids = self.laboratories.values_list('ID', flat=True)
        
        if not lab_ids:
            return 0
            
        # Récupérer tous les membres des laboratoires
        from users.models import Researcher
        member_ids = Researcher.objects.filter(
            user__teams__laboratory__in=lab_ids
        ).values_list('user_id', flat=True).distinct()
        
        if not member_ids:
            return 0
            
        # Compter les collaborations uniques
        collaborations = CoAuthor.objects.filter(
            publication__coauthors__linked_user_id__in=member_ids
        ).exclude(
            linked_user_id__in=member_ids
        ).values('author_name', 'author_orcid').distinct().count()
        
        return collaborations
    
    def get_publications_by_year(self):
        """Publications par année pour tous les laboratoires"""
        from publication.models import Publication
        
        lab_ids = self.laboratories.values_list('ID', flat=True)
        
        if not lab_ids:
            return []
            
        publications = Publication.objects.filter(
            coauthors__linked_user__teams__laboratory__in=lab_ids,
            is_validated=True
        ).distinct()
        
        # Grouper par année
        from collections import defaultdict
        year_counts = defaultdict(int)
        
        for pub in publications:
            year = pub.publication_year or 2024
            year_counts[year] += 1
        
        # Formater pour le graphique
        result = []
        current_year = timezone.now().year
        for year in range(current_year - 5, current_year + 1):
            result.append({
                'year': year,
                'publications': year_counts.get(year, 0)
            })
        
        return result
    
    def get_citations_by_year(self):
        """Citations par année"""
        from publication.models import Publication
        
        lab_ids = self.laboratories.values_list('ID', flat=True)
        
        if not lab_ids:
            return []
            
        publications = Publication.objects.filter(
            coauthors__linked_user__teams__laboratory__in=lab_ids,
            is_validated=True
        ).distinct()
        
        from collections import defaultdict
        year_citations = defaultdict(int)
        
        for pub in publications:
            year = pub.publication_year or 2024
            year_citations[year] += pub.citation_count or 0
        
        result = []
        current_year = timezone.now().year
        for year in range(current_year - 5, current_year + 1):
            result.append({
                'year': year,
                'citations': year_citations.get(year, 0)
            })
        
        return result
    
    def get_average_h_index(self):
        """H-Index moyen des chercheurs de l'institution"""
        from users.models import Researcher
        
        lab_ids = self.laboratories.values_list('ID', flat=True)
        
        if not lab_ids:
            return 0
            
        researchers = Researcher.objects.filter(
            user__teams__laboratory__in=lab_ids
        ).distinct()
        
        h_indices = [r.h_index for r in researchers if r.h_index]
        
        if not h_indices:
            return 0
            
        return sum(h_indices) / len(h_indices)
    
    def get_top_researchers(self, limit=10):
        """Top chercheurs par H-Index"""
        from users.models import Researcher
        
        lab_ids = self.laboratories.values_list('ID', flat=True)
        
        if not lab_ids:
            return []
            
        researchers = Researcher.objects.filter(
            user__teams__laboratory__in=lab_ids
        ).distinct().order_by('-h_index')[:limit]
        
        return researchers
    
    def get_laboratories_stats(self):
   
    
    
        labs_data = []
        
        for lab in self.laboratories.all():
            # Récupérer les publications du laboratoire
            publications_qs = Publication.objects.filter(
                coauthors__linked_user__teams__laboratory=lab,
                is_validated=True
            ).distinct()
            
            total_publications = publications_qs.count()
            
            # Total des citations
            total_citations = publications_qs.aggregate(total=Sum('citation_count'))['total'] or 0
            
            # Nombre de chercheurs
            researchers_count = Researcher.objects.filter(
                user__teams__laboratory=lab
            ).distinct().count()
            
            # H-Index moyen
            h_index_avg = Researcher.objects.filter(
                user__teams__laboratory=lab
            ).aggregate(avg_h=Avg('h_index'))['avg_h'] or 0
            
            labs_data.append({
                'id': lab.ID,
                'name': lab.name,
                'manager': lab.current_manager.get_full_name() if lab.current_manager else 'Non assigné',
                'publications': total_publications,
                'citations': total_citations,
                'researchers': researchers_count,
                'teams': lab.teams.count(),
                'h_index_avg': round(h_index_avg, 2),
            })
        
        # Trier par nombre de publications
        labs_data.sort(key=lambda x: x['publications'], reverse=True)
        
        return labs_data

