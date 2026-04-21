# citation/serializers.py
from rest_framework import serializers
from citation.models import Citation, DataSource


class CitationSerializer(serializers.ModelSerializer):
    citing_title  = serializers.CharField(
        source='citing_publication.title', read_only=True
    )
    cited_title   = serializers.CharField(
        source='cited_publication.title', read_only=True
    )
    source_display = serializers.CharField(
        source='get_source_display', read_only=True
    )

    class Meta:
        model  = Citation
        fields = [
            'id',
            'citing_publication', 'citing_title',
            'cited_publication',  'cited_title',
            'source', 'source_display',
            'external_id', 'citation_date',
        ]
        read_only_fields = ['id']


class CitationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Citation
        fields = [
            'citing_publication', 'cited_publication',
            'source', 'external_id', 'citation_date',
        ]

    def validate(self, attrs):
        # Une publication ne peut pas se citer elle-même
        if attrs['citing_publication'] == attrs['cited_publication']:
            raise serializers.ValidationError(
                "Une publication ne peut pas se citer elle-même."
            )
        # Doublon
        if Citation.objects.filter(
            citing_publication=attrs['citing_publication'],
            cited_publication=attrs['cited_publication']
        ).exists():
            raise serializers.ValidationError(
                "Cette relation de citation existe déjà."
            )
        return attrs