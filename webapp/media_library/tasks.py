from django.dispatch import receiver
from django_eventstream import send_event
from django_q.signals import pre_enqueue, post_execute

from logging import getLogger
logger = getLogger(__name__)


def import_products_task(project_id, shop_url, user_id=None):
    from projects.models import Project
    from .views import _detect_and_import_products
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return False, 'Project not found'
    try:
        return _detect_and_import_products(project.owner, shop_url, project=project)
    except Exception as exc:
        return False, str(exc)


@receiver(pre_enqueue)
def on_product_import_pre_enqueue(sender, task, **kwargs):
    if task.get('func') != import_products_task:
        return
    user_id = (task.get('kwargs') or {}).get('user_id')
    if user_id:
        send_event(f'user-{user_id}', 'message', {'type': 'media_library:import_started', 'status': 'importing'})


@receiver(post_execute)
def on_product_import_post_execute(sender, task, **kwargs):
    if task.get('func') != import_products_task:
        return

    project_id = task['args'][0]
    user_id = (task.get('kwargs') or {}).get('user_id')
    channel = f'user-{user_id}' if user_id else None

    from projects.models import Project
    Project.objects.filter(pk=project_id).update(product_import_in_progress=False)

    if task.get('success') and isinstance(task.get('result'), tuple):
        ok, error = task['result']
    else:
        ok, error = False, str(task.get('result') or 'Task failed unexpectedly')

    if ok:
        if channel:
            send_event(channel, 'message', {'type': 'media_library:import_completed', 'status': 'done'})
    else:
        if channel:
            send_event(channel, 'message', {'type': 'media_library:import_error', 'error': error or 'Unknown error'})
