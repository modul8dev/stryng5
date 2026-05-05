from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_default_company(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.company_id is not None:
        return
    from .models import Company
    company = Company.objects.create(name=instance.company_name or '')
    # Use update to avoid re-triggering post_save
    sender.objects.filter(pk=instance.pk).update(company=company)
    instance.company = company
