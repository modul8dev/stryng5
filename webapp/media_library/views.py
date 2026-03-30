import json
import os
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests as http_requests
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import strip_tags
from django.views.decorators.csrf import csrf_exempt
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


@login_required
def image_picker(request):
    groups = ImageGroup.objects.filter(user=request.user).prefetch_related('images')
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
    image_id = request.GET.get('image_id')
    if image_id:
        try:
            img = Image.objects.select_related('image_group').get(
                pk=int(image_id),
                image_group__user=request.user,
            )
            source_image = {'id': img.id, 'url': img.url}
        except (Image.DoesNotExist, ValueError):
            pass
    return render(request, 'media_library/image_editor_modal.html', {
        'source_image_json': json.dumps(source_image) if source_image else 'null',
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

    attachment_ids = body.get('attachment_ids', [])
    group_id = body.get('group_id')

    # Validate and load attached images
    input_images = []
    if attachment_ids:
        input_images = list(
            Image.objects.filter(pk__in=attachment_ids, image_group__user=request.user)
        )

    # Resolve or lazily create output group
    output_group = None
    if group_id:
        try:
            output_group = ImageGroup.objects.get(pk=int(group_id), user=request.user)
        except (ImageGroup.DoesNotExist, ValueError):
            pass
    if output_group is None:
        output_group = ImageGroup.objects.create(
            user=request.user,
            title='AI Generated Images',
            type=ImageGroup.GroupType.GENERATED,
        )

    # Get brand for context injection
    brand = getattr(request.user, 'brand', None)

    from social_media.ai_services import generate_editor_image
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

    return JsonResponse({
        'image': {'id': image_obj.id, 'url': image_obj.url},
        'group_id': output_group.id,
    })
