from h11 import Response
from rest_framework import serializers
from institution.models import Country, Wilaya, Ville, Institution


# ─────────────────────────────────────────
# COUNTRY
# ─────────────────────────────────────────
class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ['id', 'name']  # 🔥 utiliser id (Django standard)


# ─────────────────────────────────────────
# WILAYA
# ─────────────────────────────────────────
class WilayaSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source='country.name', read_only=True)

    class Meta:
        model = Wilaya
        fields = ['id', 'name', 'country', 'country_name']


# ─────────────────────────────────────────
# VILLE (corrigé)
# ─────────────────────────────────────────
class VilleSerializer(serializers.ModelSerializer):
    wilaya_name = serializers.CharField(source='wilaya.name', read_only=True)

    class Meta:
        model = Ville
        fields = ['id', 'name', 'wilaya', 'wilaya_name']


# ─────────────────────────────────────────
# INSTITUTION (corrigé)
# ─────────────────────────────────────────
class InstitutionSerializer(serializers.ModelSerializer):
    ville_name = serializers.CharField(source='ville.name', read_only=True)
    wilaya_name = serializers.CharField(source='ville.wilaya.name', read_only=True)
    type_display = serializers.CharField(source='get_type_display', read_only=True)

    class Meta:
        model = Institution
        fields = [
            'id',
            'name',
            'description',
            'type',
            'type_display',
            'website',
            'ville',
            'ville_name',
            'wilaya_name',
        ]


# ─────────────────────────────────────────
# DETAIL SERIALIZER
# ─────────────────────────────────────────
class InstitutionDetailSerializer(InstitutionSerializer):
    total_publications = serializers.SerializerMethodField()
    average_h_index = serializers.SerializerMethodField()
    top_researchers = serializers.SerializerMethodField()

    class Meta(InstitutionSerializer.Meta):
        fields = InstitutionSerializer.Meta.fields + [
            'total_publications',
            'average_h_index',
            'top_researchers'
        ]

    def get_total_publications(self, obj):
        return obj.get_total_publications()

    def get_average_h_index(self, obj):
        return obj.get_average_h_index()

    def get_top_researchers(self, obj):
        # ✅ Correction: utiliser obj (l'institution) pas self
        researchers = obj.get_top_researchers(limit=5)
        return [
            {
                'id': r.user.user_id,
                'name': r.user.get_full_name() or r.user.username,
                'h_index': r.h_index,
                'research_field': r.research_field or 'Non spécifié',
            }
            for r in researchers
        ]
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data
        
        # Ajouter l'adresse complète
        address_parts = []
        if instance.ville:
            address_parts.append(instance.ville.name)
            if instance.ville.wilaya:
                address_parts.append(instance.ville.wilaya.name)
                if instance.ville.wilaya.country:
                    address_parts.append(instance.ville.wilaya.country.name)
        
        data['full_address'] = ', '.join(address_parts) if address_parts else 'No address information'
        
        return Response(data)