import json
import os
from collections import Counter
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests as http_requests
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.http import HttpResponse, JsonResponse

from credits.constants import IMAGE_GENERATION_COST
from credits.models import available_credits, spend_credits
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import strip_tags
from django.views.decorators.csrf import csrf_exempt
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import MediaFormSet, MediaGroupForm
from .image_heuristics import (
    _normalize_media_identity,
    _page_context_from_crawl_doc,
    _select_distinct_product_media_urls,
)
from .models import Media, MediaGroup


def _accept_layer_response():
    """Return a response that tells Unpoly to close the current modal layer."""
    response = HttpResponse(status=204)
    response['X-Up-Accept-Layer'] = 'null'
    return response


@login_required
def catalog(request):
    groups = MediaGroup.objects.filter(project=request.project).prefetch_related('media_items')
    group_types = MediaGroup.GroupType.choices
    return render(request, 'media_library/catalog.html', {'groups': groups, 'group_types': group_types})



@login_required
def media_group_create(request):
    if request.method == 'POST':
        form = MediaGroupForm(request.POST)
        formset = MediaFormSet(request.POST, request.FILES)
        if form.is_valid() and formset.is_valid():
            group = form.save(commit=False)
            group.user = request.user
            group.project = request.project
            group.type = request.GET.get('type', MediaGroup.GroupType.MANUAL)
            group.save()
            formset.instance = group
            formset.save()
            return _accept_layer_response()
    else:
        form = MediaGroupForm()
        formset = MediaFormSet()
    return render(request, 'media_library/media_group_form.html', {
        'form': form,
        'formset': formset,
        'is_edit': False,
    })


@login_required
def media_group_edit(request, pk):
    group = get_object_or_404(MediaGroup, pk=pk, project=request.project)
    if request.method == 'POST':
        form = MediaGroupForm(request.POST, instance=group)
        formset = MediaFormSet(request.POST, request.FILES, instance=group)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return _accept_layer_response()
    else:
        form = MediaGroupForm(instance=group)
        formset = MediaFormSet(instance=group)
    return render(request, 'media_library/media_group_form.html', {
        'form': form,
        'formset': formset,
        'group': group,
        'is_edit': True,
    })


@login_required
@require_POST
def media_group_delete(request, pk):
    group = get_object_or_404(MediaGroup, pk=pk, project=request.project)
    group.delete()
    next_url = request.POST.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        redirect_to = next_url
    else:
        redirect_to = reverse('media_library:media_group_list')
    response = redirect(redirect_to)
    response['X-Up-Events'] = '[{"type":"media_library:changed"}]'
    return response


def _is_shopify(base_url):
    """Return True if base_url responds like a Shopify store."""
    graphql_url = f'{base_url}/api/2026-01/graphql.json'
    try:
        resp = http_requests.post(
            graphql_url,
            json={'query': '{ shop { name } }'},
            headers={'Content-Type': 'application/json'},
            timeout=10,
        )
        # Shopify returns 401/403 without a storefront token; non-Shopify sites differ
        return resp.status_code in (200, 401, 403)
    except http_requests.RequestException:
        return False


def _is_woocommerce(base_url):
    """Return True if base_url exposes the WooCommerce Store API."""
    api_url = f'{base_url}/wp-json/wc/store/v1/products'
    try:
        resp = http_requests.get(
            api_url,
            params={'page': 1, 'per_page': 1},
            headers={'Content-Type': 'application/json'},
            timeout=10,
        )
        return resp.status_code == 200
    except http_requests.RequestException:
        return False


def _import_shopify_products(user, base_url, project=None):
    """
    Import products and media from a Shopify store.
    Returns a tuple (success: bool, error: str or None).
    """
    parsed = urlparse(base_url)
    shop_domain = parsed.hostname

    # Fetch all products via the public /products.json endpoint
    all_products = []
    page = 1
    while page <= 20:
        products_url = f'https://{shop_domain}/products.json?limit=250&page={page}'
        try:
            resp = http_requests.get(products_url, timeout=30)
            resp.raise_for_status()
            products = resp.json().get('products', [])
        except http_requests.RequestException:
            break
        if not products:
            break
        all_products.extend(products)
        page += 1

    if not all_products:
        return False, 'No products found in this store.'

    # Create a MediaGroup per product with its media items
    for product in all_products:
        title = product.get('title', 'Untitled Product')
        body_html = product.get('body_html') or ''
        description = strip_tags(body_html).strip()[:500]

        product_url = f'https://{shop_domain}/products/{product.get("handle", "")}' if product.get('handle') else base_url
        group = MediaGroup.objects.create(
            user=user,
            project=project,
            title=title,
            description=description,
            source_url=product_url,
            type=MediaGroup.GroupType.PRODUCT,
        )

        for img_data in product.get('media', []):
            img_src = img_data.get('src', '')
            if not img_src:
                continue
            Media.objects.create(media_group=group, external_url=img_src)

    return True, None


def _import_woocommerce_products(user, base_url, project=None):
    """
    Import products and media from a WooCommerce store via the Store API.
    Returns a tuple (success: bool, error: str or None).
    """
    api_url = f'{base_url}/wp-json/wc/store/v1/products'

    page = 1
    per_page = 50
    all_products = []

    while page <= 40:
        try:
            resp = http_requests.get(
                api_url,
                params={'page': page, 'per_page': per_page},
                headers={'Content-Type': 'application/json'},
                timeout=30,
            )
        except http_requests.RequestException:
            return False, 'Could not connect to store. Please check the URL.'

        if resp.status_code != 200:
            break

        try:
            products = resp.json()
        except ValueError:
            return False, 'Unexpected response from the store.'

        if not isinstance(products, list):
            return False, 'Unexpected response from the store.'

        if not products:
            break

        all_products.extend(products)

        total_pages_header = resp.headers.get('X-WP-TotalPages')
        if total_pages_header:
            try:
                if page >= int(total_pages_header):
                    break
            except ValueError:
                pass

        if len(products) < per_page:
            break

        page += 1

    if not all_products:
        return False, 'No products found in this store.'

    for product in all_products:
        name = product.get('name') or 'Untitled Product'
        description_html = product.get('description') or product.get('short_description') or ''
        description = strip_tags(description_html).strip()[:500]

        product_link = product.get('permalink') or base_url
        group = MediaGroup.objects.create(
            user=user,
            project=project,
            title=name,
            description=description,
            source_url=product_link,
            type=MediaGroup.GroupType.PRODUCT,
        )

        for img_data in product.get('media', []):
            img_src = img_data.get('src', '')
            if img_src:
                Media.objects.create(media_group=group, external_url=img_src)

    return True, None


def _import_domain_with_crawl(user, base_url, project=None):
    """
    Crawl a domain with Firecrawl (up to 100 pages, skipping /blog) and create
    a MediaGroup per page from the media items and description found on each page.
    Returns (success: bool, error: str | None).
    """
    api_key = os.environ.get('FIRECRAWL_API_KEY', '')
    if not api_key:
        return False, 'FIRECRAWL_API_KEY is not configured.'

    from firecrawl import Firecrawl
    fc = Firecrawl(api_key=api_key)

    try:
        result = fc.crawl(
            base_url,
            limit=100,
            exclude_paths=['/blog.*'],
            crawl_entire_domain=True,
            scrape_options={
                'formats': ['media'],
                'only_main_content': True,
            },
        )
    except Exception as exc:
        return False, f'Failed to crawl site: {exc}'

    pages = getattr(result, 'data', None) or []
    if not pages:
        return False, 'No pages found at this URL.'

    page_contexts = []
    asset_page_counts = Counter()
    for doc in pages:
        context = _page_context_from_crawl_doc(doc, base_url)
        page_contexts.append(context)

        identities = {
            _normalize_media_identity(urljoin(context['page_url'], media_url))
            for media_url in context['media_urls']
            if media_url and not media_url.startswith('data:')
        }
        asset_page_counts.update(identity for identity in identities if identity)

    created = 0
    for context in page_contexts:
        media_urls = _select_distinct_product_media_urls(
            context['media_urls'],
            page_url=context['page_url'],
            page_title=context['title'],
            page_description=context['description'],
            asset_page_counts=asset_page_counts,
            total_pages=len(page_contexts),
        )
        if not media_urls:
            continue

        group = MediaGroup.objects.create(
            user=user,
            project=project,
            title=context['title'],
            description=context['description'],
            source_url=context['page_url'],
            type=MediaGroup.GroupType.PRODUCT,
        )
        for img_url in media_urls:
            Media.objects.create(media_group=group, external_url=img_url)
        created += 1

    if created == 0:
        return False, 'No media found on any crawled page.'

    return True, None


def _detect_and_import_products(user, shop_url, project=None):
    """
    Auto-detect whether shop_url is a WooCommerce or Shopify store, then import.
    Returns a tuple (success: bool, error: str or None).
    """
    if not shop_url.startswith(('http://', 'https://')):
        shop_url = 'https://' + shop_url

    parsed = urlparse(shop_url)
    shop_domain = parsed.hostname

    if not shop_domain or '.' not in shop_domain:
        return False, 'Please enter a valid store URL.'

    base_url = f'https://{shop_domain}'

    if _is_woocommerce(base_url):
        return _import_woocommerce_products(user, base_url, project=project)

    if _is_shopify(base_url):
        return _import_shopify_products(user, base_url, project=project)

    return _import_domain_with_crawl(user, base_url, project=project)


@login_required
def products_import(request):
    if request.method == 'POST':
        if request.project.product_import_in_progress:
            return render(request, 'media_library/products_import.html', {
                'error': 'A product import is already in progress. Please wait for it to finish.',
                'shop_url': '',
                'importing': True,
            })

        shop_url = request.POST.get('shop_url', '').strip()
        if not shop_url:
            return render(request, 'media_library/products_import.html', {
                'error': 'Please enter a store URL.',
                'shop_url': shop_url,
            })

        request.project.product_import_in_progress = True
        request.project.save(update_fields=['product_import_in_progress'])

        from django_q.tasks import async_task
        from .tasks import import_products_task
        async_task(
            import_products_task,
            request.project.pk,
            shop_url,
            user_id=request.user.pk,
        )

        return render(request, 'media_library/products_import.html', {'importing': True})

    return render(request, 'media_library/products_import.html', {
        'importing': request.project.product_import_in_progress,
    })


class _ImgSrcParser(HTMLParser):
    """Minimal HTML parser that collects all img src attributes."""

    def __init__(self):
        super().__init__()
        self.srcs = []

    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            attrs_dict = dict(attrs)
            src = attrs_dict.get('src', '').strip()
            if src:
                self.srcs.append(src)


def _import_url_media(user, page_url, project=None):
    """
    Scrape a URL with Firecrawl and create a manual MediaGroup with all found media items.
    Returns (success: bool, error: str | None).
    """
    api_key = os.environ.get('FIRECRAWL_API_KEY', '')
    if not api_key:
        return False, 'FIRECRAWL_API_KEY is not configured.'

    from firecrawl import Firecrawl  # noqa: import here to avoid startup cost
    fc = Firecrawl(api_key=api_key)

    try:
        result = fc.scrape(page_url, formats=['html'])
    except Exception as exc:
        return False, f'Failed to scrape page: {exc}'

    html_content = getattr(result, 'html', None) or (result.get('html') if isinstance(result, dict) else None) or ''

    parser = _ImgSrcParser()
    parser.feed(html_content)
    raw_srcs = parser.srcs

    # Resolve relative URLs against the page URL
    media_urls = []
    for src in raw_srcs:
        if src.startswith('data:'):
            continue
        absolute = urljoin(page_url, src)
        media_urls.append(absolute)

    if not media_urls:
        return False, 'No media found on the page.'

    # Derive a title from the scraped page metadata or the domain
    title = getattr(result, 'metadata', None)
    if isinstance(title, dict):
        title = title.get('title', '')
    elif hasattr(title, 'title'):
        title = title.title or ''
    else:
        title = ''
    if not title:
        title = urlparse(page_url).hostname or page_url

    group = MediaGroup.objects.create(
        user=user,
        project=project,
        title=title,
        source_url=page_url,
        type=MediaGroup.GroupType.PRODUCT,
    )
    for url in media_urls:
        Media.objects.create(media_group=group, external_url=url)

    return True, None


@login_required
def url_import(request):
    if request.method == 'POST':
        page_url = request.POST.get('page_url', '').strip()
        validate = URLValidator()
        try:
            validate(page_url)
        except ValidationError:
            return render(request, 'media_library/url_import.html', {
                'error': 'Please enter a valid URL.',
                'page_url': page_url,
            })

        success, error = _import_url_media(request.user, page_url, project=request.project)
        if success:
            return _accept_layer_response()

        return render(request, 'media_library/url_import.html', {
            'error': error,
            'page_url': page_url,
        })

    return render(request, 'media_library/url_import.html')


@login_required
def media_picker(request):
    groups = MediaGroup.objects.filter(project=request.project).prefetch_related('media_items')
    selected_raw = request.GET.get('selected', '')
    selected_ids = {int(s) for s in selected_raw.split(',') if s.strip().isdigit()}
    target = request.GET.get('target', 'shared')
    max_media_raw = request.GET.get('max', '')
    max_media = int(max_media_raw) if max_media_raw.isdigit() else 0
    allow_video = request.GET.get('allow_video', '1') != '0'
    groups_data = [
        {
            'id': g.id,
            'title': g.title,
            'description': g.description,
            'type': g.type,
            'media': [
                {'id': m.id, 'url': m.url, 'is_video': m.is_video}
                for m in g.media_items.all()
                if allow_video or not m.is_video
            ],
        }
        for g in groups
    ]
    if request.GET.get('format') == 'json':
        from django.http import JsonResponse
        return JsonResponse({'groups': groups_data})
    return render(request, 'media_library/media_picker.html', {
        'groups_data': groups_data,
        'selected_ids': list(selected_ids),
        'target': target,
        'max_media': max_media,
        'allow_video': allow_video,
        'create_url': reverse('media_library:media_group_create'),
        'edit_url_base': reverse('media_library:media_group_edit', kwargs={'pk': 0}),
        'picker_url': reverse('media_library:media_picker'),
    })


@login_required
def media_editor_modal(request):
    source_media = None
    quick_access_media = []
    media = request.GET.get('media')
    group_id = request.GET.get('group_id')
    if media:
        try:
            img = Media.objects.select_related('media_group').get(
                pk=int(media),
                media_group__project=request.project,
            )
            source_media = {'id': img.id, 'url': img.url}
        except (Media.DoesNotExist, ValueError):
            pass
    elif group_id:
        try:
            group = MediaGroup.objects.get(pk=int(group_id), project=request.project)
            quick_access_media = [{'id': m.id, 'url': m.url} for m in group.media_items.all()]
        except (MediaGroup.DoesNotExist, ValueError):
            pass
    return render(request, 'media_library/media_editor_modal.html', {
        'source_media_json': json.dumps(source_media) if source_media else 'null',
        'quick_access_media_json': json.dumps(quick_access_media),
        'group_id': group_id or '',
        'picker_url': reverse('media_library:media_picker'),
        'generate_url': reverse('media_library:media_editor_generate'),
    })


@login_required
@require_POST
def media_editor_generate(request):
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    prompt = body.get('prompt', '').strip()
    if not prompt:
        return JsonResponse({'error': 'Prompt is required.'}, status=400)

    # Check credits before proceeding
    if available_credits(request.user) < IMAGE_GENERATION_COST:
        return JsonResponse(
            {'error': 'Insufficient credits', 'credits_required': IMAGE_GENERATION_COST},
            status=402,
        )

    attachment_ids = body.get('attachment_ids', [])
    group_id = body.get('group_id')

    # Validate and load attached media
    input_media = []
    if attachment_ids:
        input_media = list(
            Media.objects.filter(pk__in=attachment_ids, media_group__project=request.project)
        )

    # Resolve or lazily create output group
    output_group = None
    if group_id:
        try:
            output_group = MediaGroup.objects.get(pk=int(group_id), project=request.project)
        except (MediaGroup.DoesNotExist, ValueError):
            pass
    if output_group is None:
        output_group = MediaGroup.objects.create(
            user=request.user,
            project=request.project,
            title='AI Generated Media',
            type=MediaGroup.GroupType.GENERATED,
        )

    # Get brand for context injection
    brand = getattr(request.project, 'brand', None)

    from services.ai_services import generate_editor_media
    try:
        media_obj = generate_editor_media(
            prompt=prompt,
            input_media=input_media,
            brand=brand,
            user=request.user,
            output_group=output_group,
        )
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)

    if media_obj is None:
        return JsonResponse({'error': 'Image generation failed — no media returned.'}, status=500)

    spend_credits(request.user, IMAGE_GENERATION_COST, 'Image editor generation')

    return JsonResponse({
        'media': {'id': media_obj.id, 'url': media_obj.url},
        'group_id': output_group.id,
    })
