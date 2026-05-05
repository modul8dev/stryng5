from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from allauth.account.signals import user_signed_up


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_default_company(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.company_id is not None:
        return
    from .models import Company
    company = Company.objects.create(name=instance.email or '')
    # Use update to avoid re-triggering post_save
    sender.objects.filter(pk=instance.pk).update(company=company)
    instance.company = company


@receiver(user_signed_up)
def send_welcome_email(sender, request, user, **kwargs):
    from django.contrib.sites.shortcuts import get_current_site
    from django_q.tasks import async_task
    from home.tasks import send_email_task

    site = get_current_site(request)
    dashboard_url = request.build_absolute_uri('/')

    async_task(
        send_email_task,
        'Welcome to Stryng!',
        'account/email/welcome_message.html',
        'account/email/welcome_message.txt',
        {
            'user_email': user.email,
            'dashboard_url': dashboard_url,
            'current_site': site,
        },
        user.email,
    )
