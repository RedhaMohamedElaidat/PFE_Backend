from django.db import models

class Team(models.Model):
    ID = models.AutoField(primary_key=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    laboratory = models.ForeignKey('laboratory.Laboratory', on_delete=models.SET_NULL, null=True, blank=True, related_name='teams')
    members = models.ManyToManyField('users.User', blank=True, related_name='teams')
    class Meta:
        db_table = 'team'
        ordering = ['name']
    def __str__(self):
        return self.name
    @property
    def current_leader(self):
        # Change from 'team_leaders' to 'teamleader_set'
        leader = self.teamleader_set.filter(end_date__isnull=True).first()
        return leader.user if leader else None