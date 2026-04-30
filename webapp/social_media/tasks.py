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

