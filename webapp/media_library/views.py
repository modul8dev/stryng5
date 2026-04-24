import json
import os
import re
from collections import Counter
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlparse

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

from .forms import ImageFormSet, ImageGroupForm
from .models import Image, ImageGroup


_COMMON_SECOND_LEVEL_TLDS = {
    'co.uk',
    'com.au',
    'co.nz',
    'co.jp',
    'com.br',
    'com.mx',
}

_PRODUCT_URL_HINTS = (
    '/product',
    '/products',
    '/item/',
    '/items/',
    '/catalog/product',
    '/media/catalog/product',
    '/documents/products/',
    'product_image',
    'product_',
    '/sku',
    '/gallery',
)

_NON_PRODUCT_URL_HINTS = (
    'front_item_icon',
    '/icon/',
    '_icon',
    '-icon',
    'favicon',
    'logo',
    '/logos/',
    'sprite',
    'badge',
    'avatar',
    'newsletter',
    'brand_image',
    '/brand/',
    '/brands/',
    'social',
    'share',
    'cartodb',
    'marker',
    'maptile',
    'apple-icon',
    'android-icon',
    'touch-icon',
    'manifest',
    'totebot.ai',
)

_HIGH_QUALITY_URL_HINTS = (
    'product_image',
    'zoom',
    'large',
    'full',
    'original',
    'hero',
)

_LOW_QUALITY_URL_HINTS = (
    'thumbnail',
    'thumb',
    'small',
    'mini',
    'list_item',
    'swatch',
)

_PAGE_POSITIVE_HINTS = (
    'buy',
    'add to cart',
    'sale',
    'price',
    'sku',
)

_PAGE_NEGATIVE_HINTS = (
    'about',
    'contact',
    'blog',
    'news',
    'journal',
    'faq',
    'privacy',
    'terms',
    'policy',
    'account',
    'login',
    'cart',
    'checkout',
)

_LISTING_PAGE_SEGMENTS = {
    'shop',
    'store',
    'products',
    'product',
    'category',
    'categories',
    'collection',
    'collections',
    'brand',
    'brands',
}

_MEASUREMENT_RE = re.compile(r'\b\d+(?:[.,]\d+)?\s?(g|kg|mg|ml|l|oz|lb|lbs|cl|pack|pcs|pc|ct)\b', re.IGNORECASE)
_DOUBLE_FORMAT_RE = re.compile(r'\.(jpe?g|png|gif|webp|avif)\.(webp|avif)$', re.IGNORECASE)
_DIMENSION_SUFFIX_RE = re.compile(r'([_-])\d{2,4}x\d{2,4}(?=\.[a-z0-9]+$)', re.IGNORECASE)
_AT_SCALE_SUFFIX_RE = re.compile(r'@\dx(?=\.[a-z0-9]+$)', re.IGNORECASE)
_STYLE_SEGMENT_RE = re.compile(r'/image_style/[^/]+/', re.IGNORECASE)
_GENERIC_STYLE_SEGMENT_RE = re.compile(r'/styles/[^/]+/', re.IGNORECASE)
_QUALITY_DIMENSION_RE = re.compile(r'([_-])(\d{2,4})x(\d{2,4})(?=\.[a-z0-9]+$)', re.IGNORECASE)
_PRODUCT_STYLE_SIZE_RE = re.compile(r'/product_(\d{2,4})(?:/|$)', re.IGNORECASE)


def _accept_layer_response():
    """Return a response that tells Unpoly to close the current modal layer."""
    response = HttpResponse(status=204)
    response['X-Up-Accept-Layer'] = 'null'
    return response


@login_required
def catalog(request):
    groups = ImageGroup.objects.filter(project=request.project).prefetch_related('images')
    group_types = ImageGroup.GroupType.choices
    return render(request, 'media_library/catalog.html', {'groups': groups, 'group_types': group_types})



@login_required
def image_group_create(request):
    if request.method == 'POST':
        form = ImageGroupForm(request.POST)
        formset = ImageFormSet(request.POST, request.FILES)
        if form.is_valid() and formset.is_valid():
            group = form.save(commit=False)
            group.user = request.user
            group.project = request.project
            group.type = request.GET.get('type', ImageGroup.GroupType.MANUAL)
            group.save()
            formset.instance = group
            formset.save()
            return _accept_layer_response()
    else:
        form = ImageGroupForm()
        formset = ImageFormSet()
    return render(request, 'media_library/image_group_form.html', {
        'form': form,
        'formset': formset,
        'is_edit': False,
    })


@login_required
def image_group_edit(request, pk):
    group = get_object_or_404(ImageGroup, pk=pk, project=request.project)
    if request.method == 'POST':
        form = ImageGroupForm(request.POST, instance=group)
        formset = ImageFormSet(request.POST, request.FILES, instance=group)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return _accept_layer_response()
    else:
        form = ImageGroupForm(instance=group)
        formset = ImageFormSet(instance=group)
    return render(request, 'media_library/image_group_form.html', {
        'form': form,
        'formset': formset,
        'group': group,
        'is_edit': True,
    })


@login_required
@require_POST
def image_group_delete(request, pk):
    group = get_object_or_404(ImageGroup, pk=pk, project=request.project)
    group.delete()
    next_url = request.POST.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        redirect_to = next_url
    else:
        redirect_to = reverse('media_library:image_group_list')
    response = redirect(redirect_to)
    response['X-Up-Events'] = '[{"type":"media_library:changed"}]'
    return response


@login_required
def add_url_image(request):
    error = None
    url = ''
    if request.method == 'POST':
        url = request.POST.get('url', '').strip()
        validate = URLValidator()
        try:
            validate(url)
            response = HttpResponse(status=204)
            response['X-Up-Accept-Layer'] = json.dumps({'url': url})
            return response
        except ValidationError:
            error = 'Please enter a valid image URL.'
    return render(request, 'media_library/url_image_modal.html', {'error': error, 'url': url})


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
    Import products and images from a Shopify store.
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

    # Create an ImageGroup per product with its images
    for product in all_products:
        title = product.get('title', 'Untitled Product')
        body_html = product.get('body_html') or ''
        description = strip_tags(body_html).strip()[:500]

        group = ImageGroup.objects.create(
            user=user,
            project=project,
            title=title,
            description=description,
            type=ImageGroup.GroupType.PRODUCT,
        )

        for img_data in product.get('images', []):
            img_src = img_data.get('src', '')
            if not img_src:
                continue
            Image.objects.create(image_group=group, external_url=img_src)

    return True, None


def _import_woocommerce_products(user, base_url, project=None):
    """
    Import products and images from a WooCommerce store via the Store API.
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

        group = ImageGroup.objects.create(
            user=user,
            project=project,
            title=name,
            description=description,
            type=ImageGroup.GroupType.PRODUCT,
        )

        for img_data in product.get('images', []):
            img_src = img_data.get('src', '')
            if img_src:
                Image.objects.create(image_group=group, external_url=img_src)

    return True, None


def _strip_www(host):
    host = (host or '').lower()
    if host.startswith('www.'):
        return host[4:]
    return host


def _domain_key(host):
    host = _strip_www(host)
    if not host:
        return ''

    parts = host.split('.')
    if len(parts) >= 3 and '.'.join(parts[-2:]) in _COMMON_SECOND_LEVEL_TLDS:
        return '.'.join(parts[-3:])
    if len(parts) >= 2:
        return '.'.join(parts[-2:])
    return host


def _hosts_look_related(asset_host, page_host):
    asset = _strip_www(asset_host)
    page = _strip_www(page_host)
    if not asset or not page:
        return False

    return (
        asset == page
        or asset.endswith(f'.{page}')
        or page.endswith(f'.{asset}')
        or _domain_key(asset) == _domain_key(page)
    )


def _normalize_image_path(path):
    normalized = unquote(path or '').lower()
    normalized = _STYLE_SEGMENT_RE.sub('/', normalized)
    normalized = _GENERIC_STYLE_SEGMENT_RE.sub('/', normalized)
    normalized = _DOUBLE_FORMAT_RE.sub(r'.\1', normalized)
    normalized = _DIMENSION_SUFFIX_RE.sub('', normalized)
    normalized = _AT_SCALE_SUFFIX_RE.sub('', normalized)
    normalized = re.sub(r'//+', '/', normalized)
    return normalized


def _normalize_image_identity(image_url):
    parsed = urlparse(image_url)
    normalized_path = _normalize_image_path(parsed.path)
    return f'{_domain_key(parsed.hostname)}{normalized_path}'


def _is_obvious_non_product_asset(image_url):
    parsed = urlparse(image_url)
    path = unquote(parsed.path or '').lower()
    text = f'{(parsed.netloc or "").lower()}{path}'
    return path.endswith(('.svg', '.ico')) or any(hint in text for hint in _NON_PRODUCT_URL_HINTS)


def _page_product_score(page_url='', title='', description=''):
    parsed = urlparse(page_url)
    path = unquote(parsed.path or '').lower()
    title = (title or '').lower()
    description = (description or '').lower()
    text = ' '.join(part for part in (path, title, description) if part)

    score = 0
    if _MEASUREMENT_RE.search(text):
        score += 2
    if any(hint in text for hint in _PAGE_POSITIVE_HINTS):
        score += 2
    if any(hint in text for hint in _PAGE_NEGATIVE_HINTS):
        score -= 2

    segments = [segment for segment in path.split('/') if segment]
    if segments:
        last = segments[-1]
        if last not in _LISTING_PAGE_SEGMENTS and len(last) >= 8:
            score += 1
    else:
        score -= 1

    return score


def _image_variant_quality(image_url):
    path = unquote(urlparse(image_url).path or '').lower()
    quality = 0.0

    if any(hint in path for hint in _HIGH_QUALITY_URL_HINTS):
        quality += 4
    if any(hint in path for hint in _LOW_QUALITY_URL_HINTS):
        quality -= 3

    match = _QUALITY_DIMENSION_RE.search(path)
    if match:
        width = int(match.group(2))
        height = int(match.group(3))
        quality += min(max(width, height), 2000) / 500.0

    match = _PRODUCT_STYLE_SIZE_RE.search(path)
    if match:
        quality += min(int(match.group(1)), 2000) / 400.0

    return quality


def _image_candidate_score(image_url, page_url='', page_title='', page_description='', asset_page_count=1, total_pages=1):
    page_score = _page_product_score(page_url=page_url, title=page_title, description=page_description)
    parsed = urlparse(image_url)
    path = unquote(parsed.path or '').lower()
    text = f'{(parsed.netloc or "").lower()}{path}'
    page_host = urlparse(page_url).hostname or ''

    score = page_score
    if _hosts_look_related(parsed.hostname, page_host):
        score += 1
    elif page_host:
        score -= 1

    if any(hint in text for hint in _PRODUCT_URL_HINTS):
        score += 4
    if any(hint in text for hint in _HIGH_QUALITY_URL_HINTS):
        score += 1
    if any(hint in text for hint in _LOW_QUALITY_URL_HINTS):
        score -= 1
    if _is_obvious_non_product_asset(image_url):
        score -= 5

    repeat_ratio = asset_page_count / max(total_pages, 1)
    if asset_page_count >= 3 and repeat_ratio >= 0.15:
        score -= 4
    elif asset_page_count >= 5:
        score -= 3

    return score


def _candidate_rank(candidate):
    return (
        candidate['score'],
        candidate['quality'],
        -candidate['asset_page_count'],
        -candidate['index'],
    )


def _select_distinct_product_image_urls(
    image_urls,
    page_url='',
    page_title='',
    page_description='',
    asset_page_counts=None,
    total_pages=1,
):
    asset_page_counts = asset_page_counts or Counter()
    page_score = _page_product_score(page_url=page_url, title=page_title, description=page_description)
    best_by_identity = {}

    for index, raw_url in enumerate(image_urls):
        url = (raw_url or '').strip()
        if not url or url.startswith('data:'):
            continue

        absolute_url = urljoin(page_url, url)
        identity = _normalize_image_identity(absolute_url)
        if not identity:
            continue

        asset_page_count = asset_page_counts.get(identity, 1)
        candidate = {
            'url': absolute_url,
            'index': index,
            'asset_page_count': asset_page_count,
            'score': _image_candidate_score(
                absolute_url,
                page_url=page_url,
                page_title=page_title,
                page_description=page_description,
                asset_page_count=asset_page_count,
                total_pages=total_pages,
            ),
            'quality': _image_variant_quality(absolute_url),
            'obvious_non_product': _is_obvious_non_product_asset(absolute_url),
        }

        previous = best_by_identity.get(identity)
        if previous is None or _candidate_rank(candidate) > _candidate_rank(previous):
            best_by_identity[identity] = candidate

    deduped = list(best_by_identity.values())
    selected = [candidate for candidate in deduped if candidate['score'] >= 2]

    if not selected and page_score >= 2:
        selected = [
            candidate for candidate in deduped
            if candidate['score'] >= 0 and not candidate['obvious_non_product']
        ]

    if not selected:
        selected = [
            candidate for candidate in deduped
            if candidate['score'] >= 1 and not candidate['obvious_non_product']
        ]

    if not selected:
        return []

    max_quality = max(candidate['quality'] for candidate in selected)
    if page_score <= 0 and len(selected) > 8 and max_quality < 3:
        return []

    selected.sort(key=lambda candidate: candidate['index'])
    return [candidate['url'] for candidate in selected]


def _page_context_from_crawl_doc(doc, base_url):
    image_urls = []
    for image in getattr(doc, 'images', None) or []:
        if isinstance(image, dict):
            value = image.get('src') or image.get('url') or ''
        else:
            value = getattr(image, 'src', None) or getattr(image, 'url', None) or str(image)
        value = (value or '').strip()
        if value:
            image_urls.append(value)

    metadata = getattr(doc, 'metadata', None) or {}
    if isinstance(metadata, dict):
        title = (metadata.get('title') or metadata.get('og_title') or '').strip()
        description = (metadata.get('description') or metadata.get('og_description') or '').strip()[:500]
        page_url = metadata.get('source_url') or metadata.get('url') or base_url
    else:
        title = (getattr(metadata, 'title', '') or '').strip()
        description = (getattr(metadata, 'description', '') or '').strip()[:500]
        page_url = getattr(metadata, 'source_url', '') or getattr(metadata, 'url', '') or base_url

    if not title:
        title = urlparse(page_url).path.strip('/') or urlparse(page_url).hostname or page_url

    return {
        'page_url': page_url,
        'title': title[:200],
        'description': description,
        'image_urls': image_urls,
    }


def _import_domain_with_crawl(user, base_url, project=None):
    """
    Crawl a domain with Firecrawl (up to 100 pages, skipping /blog) and create
    an ImageGroup per page from the images and description found on each page.
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
                'formats': ['images'],
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
            _normalize_image_identity(urljoin(context['page_url'], image_url))
            for image_url in context['image_urls']
            if image_url and not image_url.startswith('data:')
        }
        asset_page_counts.update(identity for identity in identities if identity)

    created = 0
    for context in page_contexts:
        image_urls = _select_distinct_product_image_urls(
            context['image_urls'],
            page_url=context['page_url'],
            page_title=context['title'],
            page_description=context['description'],
            asset_page_counts=asset_page_counts,
            total_pages=len(page_contexts),
        )
        if not image_urls:
            continue

        group = ImageGroup.objects.create(
            user=user,
            project=project,
            title=context['title'],
            description=context['description'],
            type=ImageGroup.GroupType.PRODUCT,
        )
        for img_url in image_urls:
            Image.objects.create(image_group=group, external_url=img_url)
        created += 1

    if created == 0:
        return False, 'No images found on any crawled page.'

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
        shop_url = request.POST.get('shop_url', '').strip()
        success, error = _detect_and_import_products(request.user, shop_url, project=request.project)

        if success:
            return _accept_layer_response()

        return render(request, 'media_library/products_import.html', {
            'error': error,
            'shop_url': shop_url,
        })

    return render(request, 'media_library/products_import.html')


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


def _import_url_images(user, page_url, project=None):
    """
    Scrape a URL with Firecrawl and create a manual ImageGroup with all found images.
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
    image_urls = []
    for src in raw_srcs:
        if src.startswith('data:'):
            continue
        absolute = urljoin(page_url, src)
        image_urls.append(absolute)

    if not image_urls:
        return False, 'No images found on the page.'

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

    group = ImageGroup.objects.create(
        user=user,
        project=project,
        title=title,
        type=ImageGroup.GroupType.MANUAL,
    )
    for url in image_urls:
        Image.objects.create(image_group=group, external_url=url)

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

        success, error = _import_url_images(request.user, page_url, project=request.project)
        if success:
            return _accept_layer_response()

        return render(request, 'media_library/url_import.html', {
            'error': error,
            'page_url': page_url,
        })

    return render(request, 'media_library/url_import.html')


@login_required
def image_picker(request):
    groups = ImageGroup.objects.filter(project=request.project).prefetch_related('images')
    selected_raw = request.GET.get('selected', '')
    selected_ids = {int(s) for s in selected_raw.split(',') if s.strip().isdigit()}
    target = request.GET.get('target', 'shared')
    max_images_raw = request.GET.get('max', '')
    max_images = int(max_images_raw) if max_images_raw.isdigit() else 0
    groups_data = [
        {
            'id': g.id,
            'title': g.title,
            'description': g.description,
            'type': g.type,
            'images': [{'id': img.id, 'url': img.url} for img in g.images.all()],
        }
        for g in groups
    ]
    if request.GET.get('format') == 'json':
        from django.http import JsonResponse
        return JsonResponse({'groups': groups_data})
    return render(request, 'media_library/image_picker.html', {
        'groups_data': groups_data,
        'selected_ids': list(selected_ids),
        'target': target,
        'max_images': max_images,
        'create_url': reverse('media_library:image_group_create'),
        'edit_url_base': reverse('media_library:image_group_edit', kwargs={'pk': 0}),
        'picker_url': reverse('media_library:image_picker'),
    })


@login_required
def image_editor_modal(request):
    source_image = None
    quick_access_images = []
    image_id = request.GET.get('image_id')
    group_id = request.GET.get('group_id')
    if image_id:
        try:
            img = Image.objects.select_related('image_group').get(
                pk=int(image_id),
                image_group__project=request.project,
            )
            source_image = {'id': img.id, 'url': img.url}
        except (Image.DoesNotExist, ValueError):
            pass
    elif group_id:
        try:
            group = ImageGroup.objects.get(pk=int(group_id), project=request.project)
            quick_access_images = [{'id': img.id, 'url': img.url} for img in group.images.all()]
        except (ImageGroup.DoesNotExist, ValueError):
            pass
    return render(request, 'media_library/image_editor_modal.html', {
        'source_image_json': json.dumps(source_image) if source_image else 'null',
        'quick_access_images_json': json.dumps(quick_access_images),
        'group_id': group_id or '',
        'picker_url': reverse('media_library:image_picker'),
        'generate_url': reverse('media_library:image_editor_generate'),
    })


@login_required
@require_POST
def image_editor_generate(request):
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

    # Validate and load attached images
    input_images = []
    if attachment_ids:
        input_images = list(
            Image.objects.filter(pk__in=attachment_ids, image_group__project=request.project)
        )

    # Resolve or lazily create output group
    output_group = None
    if group_id:
        try:
            output_group = ImageGroup.objects.get(pk=int(group_id), project=request.project)
        except (ImageGroup.DoesNotExist, ValueError):
            pass
    if output_group is None:
        output_group = ImageGroup.objects.create(
            user=request.user,
            project=request.project,
            title='AI Generated Images',
            type=ImageGroup.GroupType.GENERATED,
        )

    # Get brand for context injection
    brand = getattr(request.project, 'brand', None)

    from services.ai_services import generate_editor_image
    try:
        image_obj = generate_editor_image(
            prompt=prompt,
            input_images=input_images,
            brand=brand,
            user=request.user,
            output_group=output_group,
        )
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)

    if image_obj is None:
        return JsonResponse({'error': 'Image generation failed — no image returned.'}, status=500)

    spend_credits(request.user, IMAGE_GENERATION_COST, 'Image editor generation')

    return JsonResponse({
        'image': {'id': image_obj.id, 'url': image_obj.url},
        'group_id': output_group.id,
    })
