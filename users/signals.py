# users/signals.py

from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from .models import Researcher
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Researcher)
def auto_link_researcher_publications(sender, instance, created, **kwargs):
    """
    Signal déclenché quand un Researcher est créé ou mis à jour
    Lie automatiquement les publications existantes via l'ORCID
    """
    # Vérifier si l'ORCID est présent
    if not instance.orcid:
        return
    
    # Vérifier si c'est une nouvelle création OU si l'ORCID a changé
    should_link = False
    
    if created:
        # Nouveau chercheur
        should_link = True
        logger.info(f"Nouveau chercheur créé avec ORCID: {instance.orcid}")
    else:
        # Mise à jour - vérifier si l'ORCID a changé
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            if old_instance.orcid != instance.orcid:
                should_link = True
                logger.info(f"ORCID changé: {old_instance.orcid} → {instance.orcid}")
        except sender.DoesNotExist:
            pass
    
    # Lier les publications si nécessaire
    if should_link:
        try:
            from data_pipeline.link_researcher_publications import link_researcher_publications
            # Appeler la fonction de linking
            stats = link_researcher_publications(instance.user, instance.orcid)
            logger.info(f"Linking réussi: {stats['publications_linked']} publications liées")
        except Exception as e:
            logger.error(f"Erreur lors du linking: {e}")


@receiver(m2m_changed, sender=Researcher.publications.through)
def update_h_index_on_publication_change(sender, instance, action, reverse, model, pk_set, **kwargs):
    """
    Met à jour le H-index quand les publications d'un chercheur changent
    """
    if action in ['post_add', 'post_remove', 'post_clear']:
        try:
            from data_pipeline.bibliometrix_indicators import update_researcher_h_index
            update_researcher_h_index(instance.id)
            logger.info(f"H-index mis à jour pour chercheur {instance.id}")
        except Exception as e:
            logger.error(f"Erreur mise à jour H-index: {e}")


# ✅ CORRECTION : Importer le modèle Citation directement
@receiver(post_save, sender='citation.Citation')
def update_h_index_on_citation_change(sender, instance, created, **kwargs):
    """
    Met à jour le H-index des chercheurs quand une citation est ajoutée/modifiée
    """
    try:
        from users.models import Researcher
        from data_pipeline.bibliometrix_indicators import update_researcher_h_index
        
        # Trouver les chercheurs associés à la publication citée
        cited_pub = instance.cited_publication
        researchers = cited_pub.reseachers.all()
        
        for researcher in researchers:
            update_researcher_h_index(researcher.id)
            logger.info(f"H-index mis à jour pour {researcher.user.username}")
    except Exception as e:
        logger.error(f"Erreur mise à jour H-index sur citation: {e}")


# Signal pour lier automatiquement les publications quand un chercheur est créé
@receiver(post_save, sender=Researcher)
def auto_link_researcher_publications(sender, instance, created, **kwargs):
    """
    Signal déclenché quand un Researcher est créé ou mis à jour
    Lie automatiquement les publications existantes via l'ORCID
    """
    # Vérifier si l'ORCID est présent
    if not instance.orcid:
        return
    
    should_link = False
    
    if created:
        should_link = True
        logger.info(f"Nouveau chercheur créé avec ORCID: {instance.orcid}")
    else:
        try:
            old_instance = Researcher.objects.get(pk=instance.pk)
            if old_instance.orcid != instance.orcid:
                should_link = True
                logger.info(f"ORCID changé: {old_instance.orcid} → {instance.orcid}")
        except Researcher.DoesNotExist:
            pass
    
    if should_link:
        try:
            from data_pipeline.link_researcher_publications import link_researcher_publications
            stats = link_researcher_publications(instance.user, instance.orcid)
            logger.info(f"Linking réussi: {stats.get('publications_linked', 0)} publications liées")
        except Exception as e:
            logger.error(f"Erreur lors du linking: {e}")