# keywords/serializers.py
from rest_framework import serializers
from keywords.models import Keyword


class KeywordSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Keyword
        fields = ['id', 'label']


class KeywordCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Keyword
        fields = ['label']

    def validate_label(self, value):
        value = value.strip().lower()
        if Keyword.objects.filter(label=value).exists():
            raise serializers.ValidationError("Ce keyword existe déjà.")
        return value