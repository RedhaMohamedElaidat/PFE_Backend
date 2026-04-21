# team/serializers.py - Version ultra simple

from rest_framework import serializers
from team.models import Team
from users.models import User


class TeamMemberSerializer(serializers.ModelSerializer):
    """Serializer simple pour les membres d'une équipe."""
    full_name = serializers.SerializerMethodField()
    h_index = serializers.SerializerMethodField()
    research_field = serializers.SerializerMethodField()
    publication_count = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['user_id', 'username', 'email', 'first_name', 'last_name', 
                  'full_name', 'h_index', 'research_field', 'publication_count']
    
    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username
    
    def get_h_index(self, obj):
        try:
            return obj.researcher_profile.h_index if obj.researcher_profile else 0
        except:
            return 0
    
    def get_research_field(self, obj):
        try:
            return obj.researcher_profile.research_field if obj.researcher_profile else 'Non spécifié'
        except:
            return 'Non spécifié'
    
    def get_publication_count(self, obj):
        try:
            if obj.researcher_profile:
                return obj.researcher_profile.publications.count() if hasattr(obj.researcher_profile, 'publications') else 0
            return 0
        except:
            return 0


class TeamSerializer(serializers.ModelSerializer):
    laboratory_name = serializers.CharField(source='laboratory.name', read_only=True)
    current_leader = serializers.SerializerMethodField()
    member_count = serializers.IntegerField(source='members.count', read_only=True)

    class Meta:
        model = Team
        fields = ['ID', 'name', 'description', 'laboratory', 'laboratory_name', 
                  'current_leader', 'member_count']

    def get_current_leader(self, obj):
        leader = obj.current_leader
        if leader:
            return {
                'user_id': leader.user_id,
                'username': leader.username,
                'full_name': leader.get_full_name(),
                'email': leader.email,
            }
        return None


class TeamDetailSerializer(TeamSerializer):
    """Serializer enrichi avec la liste complète des membres."""
    members = TeamMemberSerializer(many=True, source='members.all')
    
    class Meta(TeamSerializer.Meta):
        fields = TeamSerializer.Meta.fields + ['members']


class TeamCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ['name', 'description', 'laboratory']

    def validate_name(self, value):
        value = value.strip()
        if Team.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("Une équipe avec ce nom existe déjà.")
        return value
    
    
    