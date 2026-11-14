"""Keep each gig's full-text search vector in step with its title and description."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.gigs.models import Gig, search_vector_expression


@receiver(post_save, sender=Gig)
def refresh_search_vector(sender, instance, raw=False, update_fields=None, **kwargs):
    if raw or (update_fields is not None and not {"title", "description"} & set(update_fields)):
        return
    Gig.objects.filter(pk=instance.pk).update(search_vector=search_vector_expression())
