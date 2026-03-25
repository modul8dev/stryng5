import json
import os
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests as http_requests
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import strip_tags
from django.views.decorators.http import require_POST

from .forms import ImageFormSet, ImageGroupForm
from .models import Image, ImageGroup


def _accept_layer_response():
    """Return a response that tells Unpoly to close the current modal layer."""
    response = HttpResponse(status=204)
    response['X-Up-Accept-Layer'] = 'null'
    return response


@login_required
def image_group_list(request):
    groups = ImageGroup.objects.filter(user=request.user, type=ImageGroup.GroupType.MANUAL).prefetch_related('images')
    return render(request, 'media_library/image_group_list.html', {'groups': groups})


@login_required
def product_list(request):
    groups = ImageGroup.objects.filter(user=request.user, type=ImageGroup.GroupType.PRODUCT).prefetch_related('images')
    return render(request, 'media_library/product_list.html', {'groups': groups})


@login_required
def image_group_create(request):
    if request.method == 'POST':
        form = ImageGroupForm(request.POST)
        formset = ImageFormSet(request.POST, request.FILES)
        if form.is_valid() and formset.is_valid():
            group = form.save(commit=False)
            group.user = request.user
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
    group = get_object_or_404(ImageGroup, pk=pk, user=request.user)
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
    group = get_object_or_404(ImageGroup, pk=pk, user=request.user)
    group.delete()
    response = redirect(reverse('media_library:image_group_list'))
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


def _import_shopify_products(user, shop_url):
    """
    Import products and images from a Shopify store.
    Returns a tuple (success: bool, error: str or None).
    """
    raw_input = shop_url

    # Normalize URL
    if not shop_url.startswith(('http://', 'https://')):
        shop_url = 'https://' + shop_url

    parsed = urlparse(shop_url)
    shop_domain = parsed.hostname

    if not shop_domain or '.' not in shop_domain:
        return False, 'Please enter a valid store URL.'

    # Verify it's a Shopify store by pinging the GraphQL endpoint
    graphql_url = f'https://{shop_domain}/api/2026-01/graphql.json'
    try:
        resp = http_requests.post(
            graphql_url,
            json={"query": "{ shop { name } }"},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
    except http_requests.RequestException:
        return False, 'Could not connect to store. Please check the URL.'

    # Shopify returns 401/403 without a valid token; non-Shopify sites differ
    if resp.status_code not in (200, 401, 403):
        return False, 'This does not appear to be a Shopify store.'

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


@login_required
def shopify_import(request):
    if request.method == 'POST':
        shop_url = request.POST.get('shop_url', '').strip()
        success, error = _import_shopify_products(request.user, shop_url)
        
        if success:
            return _accept_layer_response()
        
        return render(request, 'media_library/shopify_import.html', {
            'error': error,
            'shop_url': shop_url,
        })

    return render(request, 'media_library/shopify_import.html')


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


def _import_url_images(user, page_url):
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

        success, error = _import_url_images(request.user, page_url)
        if success:
            return _accept_layer_response()

        return render(request, 'media_library/url_import.html', {
            'error': error,
            'page_url': page_url,
        })

    return render(request, 'media_library/url_import.html')
