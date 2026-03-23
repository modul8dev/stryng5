from urllib.parse import urlparse

import requests as http_requests
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
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
    groups = ImageGroup.objects.filter(user=request.user).prefetch_related('images')
    return render(request, 'media_library/image_group_list.html', {'groups': groups})


@login_required
def image_group_create(request):
    if request.method == 'POST':
        form = ImageGroupForm(request.POST)
        formset = ImageFormSet(request.POST, request.FILES)
        if form.is_valid() and formset.is_valid():
            group = form.save(commit=False)
            group.user = request.user
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
def shopify_import(request):
    if request.method == 'POST':
        shop_url = request.POST.get('shop_url', '').strip()
        raw_input = shop_url

        # Normalize URL
        if not shop_url.startswith(('http://', 'https://')):
            shop_url = 'https://' + shop_url

        parsed = urlparse(shop_url)
        shop_domain = parsed.hostname

        if not shop_domain or '.' not in shop_domain:
            return render(request, 'media_library/shopify_import.html', {
                'error': 'Please enter a valid store URL.',
                'shop_url': raw_input,
            })

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
            return render(request, 'media_library/shopify_import.html', {
                'error': 'Could not connect to store. Please check the URL.',
                'shop_url': raw_input,
            })

        # Shopify returns 401/403 without a valid token; non-Shopify sites differ
        if resp.status_code not in (200, 401, 403):
            return render(request, 'media_library/shopify_import.html', {
                'error': 'This does not appear to be a Shopify store.',
                'shop_url': raw_input,
            })

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
            return render(request, 'media_library/shopify_import.html', {
                'error': 'No products found in this store.',
                'shop_url': raw_input,
            })

        # Create an ImageGroup per product with its images
        for product in all_products:
            title = product.get('title', 'Untitled Product')
            body_html = product.get('body_html') or ''
            description = strip_tags(body_html).strip()[:500]

            group = ImageGroup.objects.create(
                user=request.user,
                title=title,
                description=description,
            )

            for img_data in product.get('images', []):
                img_src = img_data.get('src', '')
                if not img_src:
                    continue
                try:
                    img_resp = http_requests.get(img_src, timeout=30)
                    img_resp.raise_for_status()
                except http_requests.RequestException:
                    continue

                # Derive a safe filename from the URL path
                path = urlparse(img_src).path
                filename = path.rsplit('/', 1)[-1] if path else 'image.jpg'
                if not filename:
                    filename = f'shopify_{img_data.get("id", "unknown")}.jpg'

                image_obj = Image(image_group=group)
                image_obj.image.save(filename, ContentFile(img_resp.content), save=True)

        return _accept_layer_response()

    return render(request, 'media_library/shopify_import.html')
