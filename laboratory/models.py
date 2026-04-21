# laboratory/models.py
from django.db import models
from django.contrib.admin import display


class Laboratory(models.Model):
    ID = models.AutoField(primary_key=True)
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    website = models.URLField(blank=True)
    institution = models.ForeignKey('institution.Institution', on_delete=models.SET_NULL, null=True, blank=True, related_name='laboratories')
    
    class Meta:
        db_table = 'laboratory'
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    @property
    @display(description='Current Manager')
    def current_manager(self):
        """Retourne l'utilisateur qui est le manager actuel du laboratoire"""
        try:
            from users.models import LabManager
            lab_manager = LabManager.objects.filter(
                laboratory=self, 
                end_date__isnull=True
            ).select_related('user').first()
            return lab_manager.user if lab_manager and lab_manager.user else None
        except Exception:
            return None
    
    def get_all_team_members(self):
        """Retourne tous les membres des équipes du laboratoire"""
        from users.models import User
        return User.objects.filter(teams__laboratory=self).distinct()
    
    def get_all_publications(self):
        """Retourne toutes les publications des membres du laboratoire"""
        from publication.models import Publication
        from coAuthor.models import CoAuthor
        
        member_ids = self.get_all_team_members().values_list('user_id', flat=True)
        
        if not member_ids:
            return Publication.objects.none()
        
        return Publication.objects.filter(
            coauthors__linked_user_id__in=member_ids
        ).distinct()
    
    def get_team_publications_by_year(self):
        """Retourne les publications groupées par année"""
        from django.db.models import Count
        
        publications = self.get_all_publications()
        
        return publications.values('publication_year').annotate(
            count=Count('id')
        ).order_by('publication_year')
    
    def get_collaborations(self):
        """
        Retourne les collaborations du laboratoire
        - Internes: collaborations entre membres de différentes équipes du labo
        - Externes: collaborations avec des personnes extérieures au labo
        """
        from coAuthor.models import CoAuthor
        from publication.models import Publication
        from users.models import User
        
        # Récupérer tous les membres du laboratoire
        lab_members = self.get_all_team_members()
        lab_member_ids = set(lab_members.values_list('user_id', flat=True))
        
        # Récupérer toutes les publications du laboratoire
        publications = self.get_all_publications()
        publication_ids = list(publications.values_list('id', flat=True))
        
        if not publication_ids:
            return {
                'internal_collaborators': [],
                'external_collaborators': [],
                'total_collaborators': 0,
                'internal_count': 0,
                'external_count': 0
            }
        
        # Récupérer tous les coauthors sur ces publications
        all_coauthors = CoAuthor.objects.filter(
            publication_id__in=publication_ids
        ).select_related('publication', 'linked_user')
        
        collaborators_dict = {}
        internal_collabs = []
        external_collabs = []
        
        for ca in all_coauthors:
            if not ca.publication:
                continue
            
            # Déterminer si c'est un collaborateur interne ou externe
            is_internal = ca.linked_user_id and ca.linked_user_id in lab_member_ids
            
            # Clé unique pour le collaborateur
            if ca.author_orcid:
                collab_key = ca.author_orcid
            elif ca.linked_user_id:
                collab_key = f"user-{ca.linked_user_id}"
            else:
                collab_key = f"coauthor-{ca.ID}"
            
            if collab_key not in collaborators_dict:
                # Déterminer le nom
                if ca.linked_user:
                    name = ca.linked_user.get_full_name() or ca.author_name or 'Unknown'
                else:
                    name = ca.author_name or 'Unknown'
                
                collaborators_dict[collab_key] = {
                    'id': ca.ID,
                    'name': name,
                    'orcid': ca.author_orcid,
                    'institution': self._extract_institution(ca.affiliation_at_time),
                    'type': 'internal' if is_internal else 'external',
                    'publication_count': 0,
                    'publications': []
                }
            
            collab = collaborators_dict[collab_key]
            collab['publication_count'] += 1
            
            pub_entry = {
                'id': ca.publication.id,
                'title': ca.publication.title,
                'year': ca.publication.publication_year,
            }
            
            if pub_entry not in collab['publications']:
                collab['publications'].append(pub_entry)
        
        # Séparer internes et externes
        for collab in collaborators_dict.values():
            if collab['type'] == 'internal':
                internal_collabs.append(collab)
            else:
                external_collabs.append(collab)
        
        internal_collabs.sort(key=lambda x: x['publication_count'], reverse=True)
        external_collabs.sort(key=lambda x: x['publication_count'], reverse=True)
        
        return {
            'internal_collaborators': internal_collabs,
            'external_collaborators': external_collabs,
            'total_collaborators': len(collaborators_dict),
            'internal_count': len(internal_collabs),
            'external_count': len(external_collabs)
        }
    
    def get_productivity_score(self) -> float:
        """Calcule le score de productivité du laboratoire (version simple)"""
        return self.get_all_publications().count()
    
    @property
    def teams(self):
        """Retourne les équipes du laboratoire"""
        from team.models import Team
        return Team.objects.filter(laboratory=self)
    
    @property
    def team_count(self):
        """Retourne le nombre d'équipes"""
        return self.teams.count()
    
    def _extract_institution(self, affiliation: str) -> str:
        """Extrait l'institution d'une affiliation"""
        if not affiliation:
            return 'Unknown'
        institution = affiliation.split(',')[0].strip()
        return institution if institution else 'Unknown'
    def get_researcher_count(self):
        """Nombre de chercheurs dans le laboratoire"""
        from users.models import Researcher
        
        count = Researcher.objects.filter(
            user__teams__laboratory=self
        ).distinct().count()
        
        return count
    
    def get_total_publications(self):
        """Nombre total de publications du laboratoire"""
        from publication.models import Publication
        
        publications = Publication.objects.filter(
            coauthors__linked_user__teams__laboratory=self,
            is_validated=True
        ).distinct()
        
        return publications.count()
    
    def get_total_citations(self):
        """Total des citations du laboratoire"""
        from publication.models import Publication
        from django.db.models import Sum
        
        total = Publication.objects.filter(
            coauthors__linked_user__teams__laboratory=self,
            is_validated=True
        ).aggregate(total=Sum('citation_count'))['total'] or 0
        
        return total
    
    def get_average_h_index(self):
        """H-Index moyen des chercheurs du laboratoire"""
        from users.models import Researcher
        from django.db.models import Avg
        
        avg = Researcher.objects.filter(
            user__teams__laboratory=self
        ).aggregate(avg_h=Avg('h_index'))['avg_h'] or 0
        
        return round(avg, 2)