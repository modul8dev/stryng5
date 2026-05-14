from django.dispatch import receiver
from django_eventstream import send_event
from django_q.signals import pre_enqueue, post_execute

from logging import getLogger
logger = getLogger(__name__)


def import_products_task(project_id, shop_url, user_id=None, single_url=False):
    from projects.models import Project
    from .views import _detect_and_import_products
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return False, 'Project not found'
    try:
        return _detect_and_import_products(project.owner, shop_url, project=project, single_url=single_url)
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

    if task.get('success') and isinstance(task.get('result'), tuple):
        ok, error = task['result']
    else:
        ok, error = False, str(task.get('result') or 'Task failed unexpectedly')

    # When the domain crawl import starts a batch scrape with a webhook,
    # it returns (True, 'batch_started'). In that case the webhook
    # handler will reset the flag and send the SSE event.
    if ok and error == 'batch_started':
        return

    from projects.models import Project
    Project.objects.filter(pk=project_id).update(product_import_in_progress=False)

    if ok:
        if channel:
            send_event(channel, 'message', {'type': 'media_library:import_completed', 'status': 'done'})
    else:
        if channel:
            send_event(channel, 'message', {'type': 'media_library:import_error', 'error': error or 'Unknown error'})


def crawled_url_hook(task):
    """
    Hook called by Django-Q after each process_crawled_url_task result is saved.
    Checks whether all tasks in the crawl group are done and batch_scrape.completed
    has already fired (scrape_done cache key). If so, sets product_import_in_progress
    to False and triggers deduplication exactly once via a cache lock.
    """
    args = task.args or []
    if len(args) < 2:
        return
    project_id = args[1]
    if not project_id:
        return

    group_id = f'crawl-{project_id}'
    from django.core.cache import cache
    from django_q.tasks import fetch_group, async_task

    # Only proceed if batch_scrape.completed has already fired.
    if not cache.get(f'{group_id}:scrape_done'):
        return

    expected = cache.get(f'{group_id}:expected', 0)
    if not expected:
        return

    done = len(fetch_group(group_id))
    if done < expected:
        return

    # All page tasks done — mark import finished and enqueue dedup exactly once.
    from projects.models import Project
    Project.objects.filter(pk=int(project_id)).update(product_import_in_progress=False)

    if cache.add(f'{group_id}:dedup_triggered', True, timeout=3600):
        async_task(deduplicate_project_media_task, int(project_id), group_id)


def process_crawled_url_task(page_data, project_id, user_id, summary_method='ai'):
    """
    Process a single page from a Firecrawl batch-scrape webhook event.
    Extracts images from the markdown/HTML, generates a summary, and creates
    a MediaGroup with Media items.
    """
    import re
    from urllib.parse import urljoin, urlparse
    from django.contrib.auth import get_user_model
    from django.utils.html import strip_tags
    from projects.models import Project
    from .models import Media, MediaGroup

    if not project_id:
        return

    try:
        project = Project.objects.get(pk=int(project_id))
    except (Project.DoesNotExist, ValueError):
        return

    User = get_user_model()
    user = None
    if user_id:
        try:
            user = User.objects.get(pk=int(user_id))
        except (User.DoesNotExist, ValueError):
            pass
    if user is None:
        user = project.owner

    # Extract fields from the page data (handles both dict and object forms)
    if isinstance(page_data, dict):
        markdown = page_data.get('markdown') or ''
        html_content = page_data.get('html') or ''
        meta = page_data.get('metadata') or {}
    else:
        markdown = getattr(page_data, 'markdown', '') or ''
        html_content = getattr(page_data, 'html', '') or ''
        meta = getattr(page_data, 'metadata', None) or {}
        if not isinstance(meta, dict):
            meta = {}

    page_url = meta.get('sourceURL') or ''
    title = meta.get('title') or meta.get('ogTitle') or ''
    if not title:
        title = urlparse(page_url).hostname or page_url or 'Untitled Page'

    # ── Extract image URLs from markdown ![alt](url) patterns ────────────
    md_images = re.findall(r'!\[.*?\]\((.*?)\)', markdown)

    # ── Extract image URLs from HTML <img> tags ──────────────────────────
    from .views import _ImgSrcParser
    parser = _ImgSrcParser()
    if html_content:
        parser.feed(html_content)

    raw_urls = md_images + parser.srcs

    # Resolve relative URLs and deduplicate
    seen = set()
    raw_media_urls = []
    for src in raw_urls:
        if not src or src.startswith('data:'):
            continue
        absolute = urljoin(page_url, src) if page_url else src
        if absolute not in seen:
            seen.add(absolute)
            raw_media_urls.append(absolute)

    if not raw_media_urls:
        return

    # ── Apply per-page heuristics to filter obvious non-product images ────
    from .image_heuristics import _select_distinct_product_media_urls
    description_text = strip_tags(markdown).strip()[:500] if markdown else ''
    media_urls = _select_distinct_product_media_urls(
        raw_media_urls,
        page_url=page_url,
        page_title=title,
        page_description=description_text,
    )
    if not media_urls:
        return

    # ── Generate title and summary ────────────────────────────────────────
    if summary_method == 'ai' and markdown:
        try:
            from django.conf.global_settings import LANGUAGES
            language_code = getattr(project, 'language', '') or 'en'
            language_name = dict(LANGUAGES).get(language_code, 'English')
            from services.ai_services import summarize_page_markdown
            result = summarize_page_markdown(markdown, language_name=language_name)
            if result.get('title'):
                title = result['title']
            description = result.get('summary', '')
        except Exception:
            description = strip_tags(markdown).strip()[:500]
    else:
        description = strip_tags(markdown).strip()[:500] if markdown else ''

    # ── Create MediaGroup + Media items ──────────────────────────────────
    group = MediaGroup.objects.create(
        user=user,
        project=project,
        title=title[:2000],
        description=description,
        source_url=page_url[:2000] if page_url else '',
        type=MediaGroup.GroupType.PRODUCT,
    )
    for img_url in media_urls:
        Media.objects.create(
            media_group=group,
            external_url=img_url,
            source_type=Media.SourceType.IMPORTED,
        )


def deduplicate_project_media_task(project_id, group_id=None):
    """
    Run cross-group deduplication for all PRODUCT MediaGroups belonging to a project.
    Removes images that appear across many groups (site-wide repeated assets such as
    social icons, logos, and nav images) and deletes any MediaGroups left empty.
    Cleans up the Django-Q group results and cache keys when done.
    """
    from projects.models import Project
    from .image_heuristics import deduplicate_media_for_project

    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return

    deduplicate_media_for_project(project)

    if group_id:
        from django_q.tasks import delete_group
        from django.core.cache import cache
        delete_group(group_id, tasks=True)
        cache.delete_many([
            f'{group_id}:expected',
            f'{group_id}:scrape_done',
            f'{group_id}:dedup_triggered',
        ])