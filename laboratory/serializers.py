# laboratory/serializers.py - ASSUREZ-VOUS D'AVOIR CES MÉTHODES

from rest_framework import serializers
from laboratory.models import Laboratory


class LaboratorySerializer(serializers.ModelSerializer):
    institution_name = serializers.CharField(source='institution.name', read_only=True)
    current_manager_name = serializers.SerializerMethodField()
    team_count = serializers.IntegerField(source='teams.count', read_only=True)

    class Meta:
        model = Laboratory
        fields = [
            'ID', 'name', 'description', 'website',
            'institution', 'institution_name',
            'current_manager_name', 'team_count',
        ]

    def get_current_manager_name(self, obj):
        manager = obj.current_manager
        if manager:
            return manager.get_full_name() or manager.username
        return None


class LaboratoryDetailSerializer(LaboratorySerializer):
    """Serializer enrichi avec les équipes et le score de productivité"""
    teams = serializers.SerializerMethodField()
    productivity_score = serializers.SerializerMethodField()
    total_publications = serializers.SerializerMethodField()
    total_researchers = serializers.SerializerMethodField()

    class Meta(LaboratorySerializer.Meta):
        fields = LaboratorySerializer.Meta.fields + [
            'teams', 'productivity_score', 'total_publications', 'total_researchers'
        ]

    def get_teams(self, obj):
        from team.serializers import TeamSerializer
        return TeamSerializer(obj.teams.all(), many=True).data

    def get_productivity_score(self, obj):
        return obj.get_productivity_score()

    def get_total_publications(self, obj):
        return obj.get_all_publications().count()

    def get_total_researchers(self, obj):
        return obj.get_all_team_members().count()


class LaboratoryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Laboratory
        fields = ['name', 'description', 'website', 'institution']

    def validate_name(self, value):
        value = value.strip()
        if Laboratory.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("Un laboratoire avec ce nom existe déjà.")
        return value