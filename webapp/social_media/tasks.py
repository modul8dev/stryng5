"""
Django-Q2 tasks for social media publishing.
"""

import logging

from django.utils import timezone
from django_q.tasks import async_task
from django_eventstream import send_event

from .models import SocialMediaPost
from .publisher import publish_post

logger = logging.getLogger(__name__)


def _notify_publish_done(post_id, post_status, results):
    """Send SSE event so the browser knows publishing has completed."""
    successes = [p for p, r in results.items() if r['success']]
    failures = {p: r['error'] for p, r in results.items() if not r['success']}

    # Resolve user_id from the post
    try:
        user_id = SocialMediaPost.objects.values_list('user_id', flat=True).get(pk=post_id)
    except SocialMediaPost.DoesNotExist:
        logger.error('_notify_publish_done: post %d not found', post_id)
        return

    try:
        send_event(f'user-{user_id}', 'message', {
            'type': 'publish-done',
            'post_id': post_id,
            'status': post_status,
            'successes': successes,
            'failures': failures,
        })
    except Exception:
        logger.exception('Failed to send SSE publish-done event for post %d', post_id)


def publish_post_task(post_id, base_url=''):
    """
    Async task: marks post as 'publishing', calls publish_post(),
    then sets status to 'published' (any success) or 'failed' (all failed).
    """
    try:
        post = SocialMediaPost.objects.select_related('project').get(pk=post_id)
    except SocialMediaPost.DoesNotExist:
        logger.error('publish_post_task: post %d not found', post_id)
        return

    post.status = 'publishing'
    post.save(update_fields=['status'])

    try:
        results = publish_post(post, post.project, base_url=base_url)
    except Exception:
        logger.exception('publish_post_task: unexpected error for post %d', post_id)
        post.status = 'failed'
        post.save(update_fields=['status'])
        _notify_publish_done(post_id, 'failed', {})
        return

    all_failed = results and all(not r['success'] for r in results.values())
    if all_failed:
        post.status = 'failed'
        post.save(update_fields=['status'])

    _notify_publish_done(post_id, post.status, results)


def check_scheduled_posts():
    """
    Periodic task (every minute): enqueue publish_post_task for all scheduled
    posts whose scheduled_at is in the past.
    """
    now = timezone.now()
    posts = SocialMediaPost.objects.filter(
        status='scheduled',
        scheduled_at__lte=now,
    ).select_related('project')

    for post in posts:
        # Mark as publishing immediately to prevent double-queuing on next tick
        post.status = 'publishing'
        post.save(update_fields=['status'])
        async_task('social_media.tasks.publish_post_task', post.pk)
        logger.info('Enqueued publish task for scheduled post %d (%s)', post.pk, post.title)


def _notify_generation_done(post_id, processing_status, error='', shared_text='', media=None):
    """Send SSE event so the browser knows generation has completed."""
    try:
        user_id = SocialMediaPost.objects.values_list('user_id', flat=True).get(pk=post_id)
    except SocialMediaPost.DoesNotExist:
        logger.error('_notify_generation_done: post %d not found', post_id)
        return

    payload = {
        'type': 'generation-done',
        'post_id': post_id,
        'processing_status': processing_status,
        'error': error,
    }
    if processing_status == 'completed':
        payload['shared_text'] = shared_text
        payload['media'] = media or []

    try:
        send_event(f'user-{user_id}', 'message', payload)
    except Exception:
        logger.exception('Failed to send SSE generation-done event for post %d', post_id)


def generate_post_task(post_id, brand_id, topic, post_type, seed_media_ids, platforms):
    """
    Async task: generates post text and media via AI, then saves results to the post.
    Sets processing_status to 'generating' -> 'completed' or 'error'.
    """
    from brand.models import Brand
    from media_library.models import Media
    from credits.models import available_credits, spend_credits
    from credits.constants import IMAGE_GENERATION_COST
    from services.ai_services import generate_post_text, generate_post_media

    try:
        post = SocialMediaPost.objects.select_related('project', 'user').get(pk=post_id)
    except SocialMediaPost.DoesNotExist:
        logger.error('generate_post_task: post %d not found', post_id)
        return

    try:
        brand = Brand.objects.get(pk=brand_id)
    except Brand.DoesNotExist:
        logger.error('generate_post_task: brand %d not found', brand_id)
        post.processing_status = 'error'
        post.save(update_fields=['processing_status'])
        _notify_generation_done(post_id, 'error', 'Brand not found')
        return

    seed_media = list(
        Media.objects.filter(
            id__in=seed_media_ids,
            media_group__project=post.project,
        )
    ) if seed_media_ids else []

    try:
        # Generate text
        text = generate_post_text(brand, topic, post_type, seed_media, platforms)
        if text:
            post.shared_text = text

        # Generate media
        try:
            if available_credits(post.user) >= IMAGE_GENERATION_COST:
                media = generate_post_media(brand, topic, post_type, seed_media, post.user, project=post.project)
                if media:
                    spend_credits(post.user, IMAGE_GENERATION_COST, 'Post media generation')
                    from .models import SocialMediaPostMedia
                    SocialMediaPostMedia.objects.create(
                        post=post,
                        media=media,
                        sort_order=0,
                    )
        except Exception:
            logger.exception('generate_post_task: media generation failed for post %d (text ok)', post_id)

        post.processing_status = 'completed'
        post.save(update_fields=['shared_text', 'processing_status'])
        media_items = [
            {'id': m.media.id, 'url': m.media.url, 'is_video': m.media.is_video}
            for m in post.shared_media.select_related('media').order_by('sort_order')
        ]
        _notify_generation_done(post_id, 'completed', shared_text=post.shared_text, media=media_items)

    except Exception as e:
        logger.exception('generate_post_task: failed for post %d', post_id)
        post.processing_status = 'error'
        post.save(update_fields=['processing_status'])
        _notify_generation_done(post_id, 'error', str(e))
