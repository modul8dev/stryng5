from django.dispatch import receiver
from django_eventstream import send_event
from django_q.signals import pre_enqueue, post_execute

from logging import getLogger
logger = getLogger(__name__)


def scrape_brand_task(brand_id, url, user_id=None, task_name="scrape_brand"):
    """
    Django-Q2 task: scrape brand data for a given brand and URL.
    Returns (success, error). Status updates and SSE are handled by post_execute signal.
    """
    from .models import Brand
    from .views import _scrape_brand_data

    try:
        brand = Brand.objects.select_related('project', 'user').get(pk=brand_id)
    except Brand.DoesNotExist:
        return False, 'Brand not found'

    try:
        return _scrape_brand_data(brand.user, brand.project, url)
    except Exception as exc:
        return False, str(exc)


# ── Pre-enqueue signal handler ──────────────────────────────────────────────
@receiver(pre_enqueue)
def on_brand_scrape_pre_enqueue(sender, task, **kwargs):
    """Send SSE scraping_started event before the brand scrape task hits the queue."""
    if task.get('func') != scrape_brand_task:
        return
    user_id = (task.get('kwargs') or {}).get('user_id')
    if user_id:
        send_event(f'user-{user_id}', 'message', {'type': 'brand:scrape_started', 'status': 'scraping'})
        logger.info('Sent brand:scrape_started event for user %d', user_id)


# ── Post-execute signal handler ─────────────────────────────────────────────
@receiver(post_execute)
def on_brand_scrape_post_execute(sender, task, **kwargs):
    """Update brand status and send SSE after the task finishes (or crashes)."""
    if task.get('func') != scrape_brand_task:
        return

    from .models import Brand

    brand_id = task['args'][0]
    user_id = (task.get('kwargs') or {}).get('user_id')
    channel = f'user-{user_id}' if user_id else None

    # task['success'] is False when the task raised an unhandled exception
    if task.get('success') and isinstance(task.get('result'), tuple):
        scrape_ok, error = task['result']
    else:
        scrape_ok, error = False, str(task.get('result') or 'Task failed unexpectedly')

    if scrape_ok:
        Brand.objects.filter(pk=brand_id).update(
            processing_status=Brand.ProcessingStatus.IDLE,
            scrape_error='',
        )
        if channel:
            send_event(channel, 'message', {'type': 'brand:scrape_completed', 'status': 'complete'})
    else:
        Brand.objects.filter(pk=brand_id).update(
            processing_status=Brand.ProcessingStatus.IDLE,
            scrape_error=error or '',
        )
        if channel:
            send_event(channel, 'message', {'type': 'brand:scrape_error', 'error': error or 'Unknown error'})
