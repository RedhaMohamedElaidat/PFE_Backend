from rest_framework import serializers
from publication.models import Publication
from journal.serializers import JournalSerializer
from keywords.serializers import KeywordSerializer
from coAuthor.serializers import CoAuthorSerializer


# ─────────────────────────────────────────────
# 🔹 PUBLICATION DETAIL SERIALIZER
# ─────────────────────────────────────────────
class PublicationSerializer(serializers.ModelSerializer):

    journal_detail = JournalSerializer(source='journal', read_only=True)
    keywords_detail = KeywordSerializer(source='keywords', many=True, read_only=True)

    type_display = serializers.CharField(source='get_type_display', read_only=True)
    impact_factor = serializers.SerializerMethodField()

    # 🔥 NEW: Coauthors integration
    coauthors = CoAuthorSerializer(many=True, read_only=True)
    coauthors_count = serializers.SerializerMethodField()

    class Meta:
        model = Publication
        fields = [
            'id',
            'title',
            'abstract',
            'publication_year',

            'doi',
            'type',
            'type_display',

            'institution',
            'journal',
            'journal_detail',

            'keywords',
            'keywords_detail',

            # 🔥 Coauthors
            'coauthors',
            'coauthors_count',

            'citation_count',
            'altmetric_score',
            'is_validated',

            'impact_factor',
        ]

        read_only_fields = ['id', 'citation_count']

    def get_impact_factor(self, obj):
        return obj.get_impact_factor()

    def get_coauthors_count(self, obj):
        return obj.coauthors.count()


# ─────────────────────────────────────────────
# 🔹 CREATE SERIALIZER
# ─────────────────────────────────────────────
class PublicationCreateSerializer(serializers.ModelSerializer):

    class Meta:
        model = Publication
        fields = [
            'title',
            'abstract',
            'publication_year',
            'doi',
            'type',
            'institution',
            'journal',
            'keywords',
            'altmetric_score',
        ]

    def validate_publication_year(self, value):
        from django.utils import timezone

        current_year = timezone.now().year

        if value and (value < 1900 or value > current_year):
            raise serializers.ValidationError(
                f"L'année doit être entre 1900 et {current_year}."
            )
        return value

    def validate_doi(self, value):
        if value:
            value = value.strip()
            if not value.startswith('10.'):
                raise serializers.ValidationError(
                    "DOI invalide — doit commencer par '10.'"
                )
        return value


# ─────────────────────────────────────────────
# 🔹 LIST SERIALIZER (LIGHTWEIGHT)
# 🔥 FIXED: Now includes journal_detail with impact_factor
# ─────────────────────────────────────────────
class PublicationListSerializer(serializers.ModelSerializer):

    journal_name = serializers.CharField(source='journal.name', read_only=True)
    journal_detail = JournalSerializer(source='journal', read_only=True)
    type_display = serializers.CharField(source='get_type_display', read_only=True)

    # 🔥 NEW: useful for UI
    coauthors_count = serializers.SerializerMethodField()

    class Meta:
        model = Publication
        fields = [
            'id',
            'title',
            'publication_year',

            'type',
            'type_display',

            'doi',
            'citation_count',
            'is_validated',

            'journal_name',
            'journal_detail',
            'altmetric_score',

            # 🔥 NEW
            'coauthors_count',
        ]

    def get_coauthors_count(self, obj):
        return obj.coauthors.count()


# ─────────────────────────────────────────────
# 🔹 ADMIN VALIDATION SERIALIZER
# ─────────────────────────────────────────────
class PublicationValidateSerializer(serializers.ModelSerializer):

    class Meta:
        model = Publication
        fields = ['is_validated']