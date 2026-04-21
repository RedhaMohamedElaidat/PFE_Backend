# journal/serializers.py
from rest_framework import serializers
from journal.models import Journal


class JournalSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Journal
        fields = ['id', 'name', 'impact_factor', 'issn']


class JournalCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Journal
        fields = ['name', 'impact_factor', 'issn']

    def validate_issn(self, value):
        if value and len(value.replace('-', '')) not in [8, 13]:
            raise serializers.ValidationError("ISSN invalide — format attendu : XXXX-XXXX")
        return value

    def validate_impact_factor(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("L'impact factor ne peut pas être négatif.")
        return value