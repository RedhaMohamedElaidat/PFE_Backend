from rest_framework import serializers
from coAuthor.models import CoAuthor
from django.db import models


class CoAuthorSerializer(serializers.ModelSerializer):
    # ── Publication ─────────────────────────
    publication_title = serializers.CharField(
        source='publication.title', read_only=True
    )
    publication_year = serializers.IntegerField(
        source='publication.publication_year', read_only=True
    )
    publication_doi = serializers.CharField(
        source='publication.doi', read_only=True
    )

    # ── Display ─────────────────────────────
    contribution_display = serializers.CharField(
        source='get_contribution_type_display', read_only=True
    )

    # ── User Info (if linked) ───────────────
    user_email = serializers.SerializerMethodField()
    user_full_name = serializers.SerializerMethodField()
    is_registered = serializers.BooleanField(read_only=True)
    display_name = serializers.CharField(read_only=True)

    # ── Metrics (optional) ──────────────────
    h_index = serializers.SerializerMethodField()
    total_citations = serializers.SerializerMethodField()
    publication_count = serializers.SerializerMethodField()

    class Meta:
        model = CoAuthor
        fields = [
            'ID',
            'publication', 
            'publication_title',
            'publication_year',
            'publication_doi',

            # OpenAlex data
            'author_name',
            'author_orcid',
            'openalex_id',

            # display
            'display_name',
            'is_registered',
            'user_email',
            'user_full_name',

            'contribution_type', 
            'contribution_display',
            'author_order',
            'affiliation_at_time',

            # Metrics
            'h_index',
            'total_citations',
            'publication_count',

            # Timestamps
            'created_at',
            'updated_at',
        ]

        read_only_fields = ['ID', 'created_at', 'updated_at']

    def get_user_email(self, obj):
        if obj.linked_user:
            return obj.linked_user.email
        return None

    def get_user_full_name(self, obj):
        if obj.linked_user:
            return obj.linked_user.get_full_name()
        return None

    def get_h_index(self, obj):
        """Récupère le h-index si l'utilisateur est lié"""
        try:
            if obj.linked_user and hasattr(obj.linked_user, 'researcher_profile'):
                return obj.linked_user.researcher_profile.h_index
        except Exception:
            pass
        return 0

    def get_total_citations(self, obj):
        """Récupère le nombre total de citations si l'utilisateur est lié"""
        try:
            if obj.linked_user and hasattr(obj.linked_user, 'researcher_profile'):
                return obj.linked_user.researcher_profile.total_citations or 0
        except Exception:
            pass
        return 0

    def get_publication_count(self, obj):
        """Récupère le nombre total de publications si l'utilisateur est lié"""
        try:
            if obj.linked_user and hasattr(obj.linked_user, 'researcher_profile'):
                return obj.linked_user.researcher_profile.publication_count or 0
        except Exception:
            pass
        return 0


class CoAuthorCreateSerializer(serializers.ModelSerializer):
    """Sérializer pour la création individuelle avec validation d'unicité par ordre"""
    
    class Meta:
        model = CoAuthor
        fields = [
            'publication',
            'author_name',
            'author_orcid',
            'openalex_id',
            'contribution_type',
            'author_order',
            'affiliation_at_time',
            'linked_user',  # Ajouté pour permettre le lien manuel
        ]

    def validate(self, attrs):
        """
        Validation qui permet la duplication si l'ordre est différent
        """
        publication = attrs['publication']
        author_orcid = attrs.get('author_orcid')
        openalex_id = attrs.get('openalex_id')
        author_order = attrs.get('author_order', 1)
        
        # Construire la requête de vérification d'existence
        query = models.Q(publication=publication)
        
        if author_orcid:
            # Un auteur avec ORCID peut avoir plusieurs entrées avec des ordres différents
            query &= models.Q(author_orcid=author_orcid, author_order=author_order)
        elif openalex_id:
            query &= models.Q(openalex_id=openalex_id, author_order=author_order)
        else:
            # Pour les auteurs sans identifiant, on utilise le nom + ordre
            query &= models.Q(author_name=attrs['author_name'], author_order=author_order)
        
        if CoAuthor.objects.filter(query).exists():
            raise serializers.ValidationError(
                f"Ce co-auteur existe déjà pour cette publication avec l'ordre {author_order}."
            )
        
        return attrs

    def validate_author_order(self, value):
        if value < 0:  # Permettre 0 pour les entrées forcées
            raise serializers.ValidationError(
                "L'ordre doit être >= 0."
            )
        return value

    def validate_contribution_type(self, value):
        if value not in [1, 2, 3, 4, 5]:
            raise serializers.ValidationError(
                "Type de contribution invalide. Choisir entre 1 et 5."
            )
        return value


class CoAuthorBulkSerializer(serializers.Serializer):
    """Sérializer pour la création en masse avec support de duplication"""
    
    publication_id = serializers.IntegerField()
    authors = serializers.ListField(child=serializers.DictField())

    def validate_publication_id(self, value):
        from publication.models import Publication
        if not Publication.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Publication introuvable.")
        return value

    def validate_authors(self, value):
        if not value:
            raise serializers.ValidationError("Liste des auteurs vide.")

        # Vérifier chaque auteur
        orders_used = set()
        for idx, author in enumerate(value):
            if 'author_name' not in author:
                raise serializers.ValidationError(
                    f"Auteur {idx+1}: author_name requis."
                )
            
            # Vérifier que l'ordre est unique dans la liste
            order = author.get('author_order', idx + 1)
            if order in orders_used:
                raise serializers.ValidationError(
                    f"L'ordre {order} est utilisé plusieurs fois dans la liste."
                )
            orders_used.add(order)
            
            # Validation optionnelle
            if author.get('author_order', 1) < 0:
                raise serializers.ValidationError(
                    f"Auteur {idx+1}: l'ordre doit être >= 0."
                )
        
        return value

    def create(self, validated_data):
        """
        Création en masse avec gestion des conflits
        """
        from publication.models import Publication
        from coAuthor.models import CoAuthor
        
        publication_id = validated_data['publication_id']
        authors_data = validated_data['authors']
        
        publication = Publication.objects.get(pk=publication_id)
        
        created_authors = []
        errors = []
        
        for author_data in authors_data:
            try:
                # Vérifier si l'entrée existe déjà avec le même ordre
                existing = CoAuthor.objects.filter(
                    publication=publication,
                    author_order=author_data.get('author_order', 1)
                )
                
                if author_data.get('author_orcid'):
                    existing = existing.filter(author_orcid=author_data['author_orcid'])
                elif author_data.get('openalex_id'):
                    existing = existing.filter(openalex_id=author_data['openalex_id'])
                else:
                    existing = existing.filter(author_name=author_data['author_name'])
                
                if existing.exists():
                    errors.append({
                        'author': author_data.get('author_name'),
                        'error': f"Déjà existant avec l'ordre {author_data.get('author_order', 1)}"
                    })
                    continue
                
                # Créer l'entrée
                coauthor = CoAuthor.objects.create(
                    publication=publication,
                    author_name=author_data.get('author_name'),
                    author_orcid=author_data.get('author_orcid'),
                    openalex_id=author_data.get('openalex_id'),
                    contribution_type=author_data.get('contribution_type', 5),
                    author_order=author_data.get('author_order', 1),
                    affiliation_at_time=author_data.get('affiliation_at_time', ''),
                    linked_user=author_data.get('linked_user'),
                )
                created_authors.append(coauthor)
                
            except Exception as e:
                errors.append({
                    'author': author_data.get('author_name', 'Unknown'),
                    'error': str(e)
                })
        
        # Stocker les erreurs dans le contexte pour la réponse
        self.context['errors'] = errors
        
        return created_authors


class CoAuthorUpdateSerializer(serializers.ModelSerializer):
    """Sérializer pour la mise à jour avec validation"""
    
    class Meta:
        model = CoAuthor
        fields = [
            'author_name',
            'author_orcid',
            'openalex_id',
            'contribution_type',
            'author_order',
            'affiliation_at_time',
            'linked_user',
        ]
    
    def validate_author_order(self, value):
        if value < 0:
            raise serializers.ValidationError("L'ordre doit être >= 0.")
        return value
    
    def validate(self, attrs):
        # Si on change l'ordre, vérifier qu'il n'y a pas de conflit
        if 'author_order' in attrs and self.instance:
            # Vérifier si une autre entrée existe avec le même ordre pour ce même auteur
            query = CoAuthor.objects.filter(
                publication=self.instance.publication,
                author_order=attrs['author_order']
            ).exclude(pk=self.instance.pk)
            
            if self.instance.author_orcid:
                query = query.filter(author_orcid=self.instance.author_orcid)
            elif self.instance.openalex_id:
                query = query.filter(openalex_id=self.instance.openalex_id)
            else:
                query = query.filter(author_name=self.instance.author_name)
            
            if query.exists():
                raise serializers.ValidationError(
                    f"Un auteur existe déjà avec l'ordre {attrs['author_order']}."
                )
        
        return attrs


class CoAuthorCollaborationSerializer(serializers.ModelSerializer):
    """
    Sérializer spécifique pour les collaborations
    """
    publication_title = serializers.CharField(source='publication.title')
    publication_year = serializers.IntegerField(source='publication.publication_year')
    publication_citations = serializers.IntegerField(source='publication.citation_count')
    
    coauthor_name = serializers.SerializerMethodField()
    coauthor_email = serializers.SerializerMethodField()
    coauthor_h_index = serializers.SerializerMethodField()
    collaboration_count = serializers.SerializerMethodField()
    
    class Meta:
        model = CoAuthor
        fields = [
            'publication_title',
            'publication_year',
            'publication_citations',
            'author_order',
            'contribution_type',
            'coauthor_name',
            'coauthor_email',
            'coauthor_h_index',
            'collaboration_count',
        ]
    
    def get_coauthor_name(self, obj):
        if obj.linked_user:
            return obj.linked_user.get_full_name()
        return obj.author_name
    
    def get_coauthor_email(self, obj):
        if obj.linked_user:
            return obj.linked_user.email
        return None
    
    def get_coauthor_h_index(self, obj):
        try:
            if obj.linked_user and hasattr(obj.linked_user, 'researcher_profile'):
                return obj.linked_user.researcher_profile.h_index
        except Exception:
            pass
        return 0
    
    def get_collaboration_count(self, obj):
        """Nombre de collaborations entre ces deux chercheurs"""
        if not obj.linked_user:
            return 0
        
        # Compter le nombre de publications en commun
        return CoAuthor.objects.filter(
            linked_user=obj.linked_user
        ).exclude(
            publication=obj.publication
        ).count()