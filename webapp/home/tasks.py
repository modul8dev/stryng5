import logging

from django.core.cache import cache
from django_eventstream import send_event

logger = logging.getLogger(__name__)


def send_email_task(subject, template_html, template_txt, context, to_email):
    """
    Generic Django-Q2 task: renders and sends a transactional email.

    Args:
        subject (str): Email subject line.
        template_html (str): Django template path for the HTML body (MJML or plain HTML).
        template_txt (str): Django template path for the plain-text fallback body.
        context (dict): Template context passed to both templates.
        to_email (str): Recipient email address.
    """
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string
    from django.conf import settings

    try:
        text_body = render_to_string(template_txt, context).strip()
        html_body = render_to_string(template_html, context).strip()

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
        )
        msg.attach_alternative(html_body, 'text/html')
        msg.send()
        logger.info('Email "%s" sent to %s', subject, to_email)
    except Exception:
        logger.exception('Failed to send email "%s" to %s', subject, to_email)

CACHE_TIMEOUT = 300  # 5 minutes


def generate_inspiration_card_task(project_id, user_id, group_id, slot_id):
    """
    Django-Q2 task: generate a single AI inspiration card for one product group.
    Stores card data in cache and notifies the user via SSE when done.
    """
    from brand.models import Brand
    from media_library.models import MediaGroup, Media
    from services.ai_services import suggest_topic

    cache_key = f'inspiration_card_{slot_id}'
    card = None
    try:
        try:
            brand = Brand.objects.get(project_id=project_id)
            if not brand.has_data:
                brand = None
        except Brand.DoesNotExist:
            brand = None

        if brand:
            group = (
                MediaGroup.objects.filter(pk=group_id, project_id=project_id)
                .prefetch_related('media_items')
                .first()
            )
            if group:
                media = list(group.media_items.exclude(source_type=Media.SourceType.GENERATED).all())
                seed_media = media[:2]
                try:
                    topics = suggest_topic(brand, seed_media)
                    topic = topics[0] if topics else ''
                except Exception:
                    logger.exception('Failed to generate inspiration topic for group %d', group.pk)
                    topic = ''

                first_media = media[0] if media else None
                seed_media_ids = ','.join(str(img.id) for img in seed_media)
                card = {
                    'group_title': group.title,
                    'media': first_media.id if first_media else None,
                    'topic': topic,
                    'seed_media_ids': seed_media_ids,
                }
    except Exception:
        logger.exception('generate_inspiration_card_task failed for project %d group %d', project_id, group_id)

    cache.set(cache_key, {'project_id': project_id, 'card': card}, timeout=CACHE_TIMEOUT)
    send_event(f'user-{user_id}', 'message', {
        'type': 'inspiration:card_ready',
        'slot_id': slot_id,
        'cache_key': cache_key,
    })
    return True
