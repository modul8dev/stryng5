import json
import os
from urllib.parse import urljoin, urlparse

import requests as http_requests
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from media_library.models import Image, ImageGroup
from media_library.views import _import_shopify_products, _import_url_images
from prompts.brand_extract import BRAND_EXTRACT_PROMPT

from media_library.models import ImageGroup
from .forms import BrandForm, ScrapeURLForm
from .models import Brand


# ── Unpoly modal helper ─────────────────────────────────────────────────────

def _accept_layer_response():
    response = HttpResponse(status=204)
    response['X-Up-Accept-Layer'] = 'null'
    return response


# ── Brand scraping ──────────────────────────────────────────────────────────


def _create_logo_image_group(user, logo_url, brand_name):
    """Create an ImageGroup containing the logo URL. Returns the group or None."""
    try:
        group = ImageGroup.objects.create(
            user=user,
            title=f'{brand_name} Logo' if brand_name else 'Brand Logo',
            type=ImageGroup.GroupType.MANUAL,
        )
        Image.objects.create(image_group=group, external_url=logo_url)
        return group
    except Exception:
        return None


def _scrape_brand_data(user, url):
    """
    Scrape a website URL to extract brand data and populate the user's Brand model.
    Also imports website images to the media library and handles Shopify stores.
    Returns (success: bool, error: str | None).
    """
    firecrawl_key = os.environ.get('FIRECRAWL_API_KEY', '')
    if not firecrawl_key:
        return False, 'FIRECRAWL_API_KEY is not configured.'

    openai_key = os.environ.get('OPENAI_API_KEY', '')
    if not openai_key:
        return False, 'OPENAI_API_KEY is not configured.'

    # ── 7a: Firecrawl scrape (markdown + branding) ──────────────────
    from firecrawl import Firecrawl
    fc = Firecrawl(api_key=firecrawl_key)

    try:
        result = fc.scrape(url, formats=['markdown', 'branding'])
    except Exception as exc:
        return False, f'Failed to scrape page: {exc}'

    markdown_content = getattr(result, 'markdown', None) or ''
    branding = getattr(result, 'branding', None)
    logo_url = branding.images.get('logo', None)

    if not markdown_content:
        return False, 'Could not retrieve page content for analysis.'

    # ── 7b: OpenAI structured extraction ────────────────────────────────────
    from openai import OpenAI
    client = OpenAI(api_key=openai_key)

    try:
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': BRAND_EXTRACT_PROMPT},
                {'role': 'user', 'content': markdown_content[:12000]},
            ],
            response_format={'type': 'json_object'},
            temperature=0.2,
        )
        extracted = json.loads(response.choices[0].message.content)
    except Exception as exc:
        return False, f'Failed to extract brand data: {exc}'

    brand_name = extracted.get('name', '').strip()
    brand_summary = extracted.get('summary', '').strip()
    brand_language = extracted.get('language', '').strip()
    brand_style_guide = extracted.get('style_guide', '').strip()

    # ── 7d: Import all website images to media library ──────────────────────
    _import_url_images(user, url)  # errors are non-fatal

    # ── 7e: Try Shopify import (silently skip if not Shopify) ───────────────
    _import_shopify_products(user, url)  # errors are non-fatal

    # ── 7c: Create logo ImageGroup ───────────────────────────────────────────
    logo_group = None
    if logo_url:
        logo_group = _create_logo_image_group(user, logo_url, brand_name)

    # ── 7f: Save brand data ─────────────────────────────────────────────────
    brand, _ = Brand.objects.get_or_create(user=user)
    brand.website_url = url
    brand.name = brand_name
    brand.summary = brand_summary
    brand.language = brand_language
    brand.style_guide = brand_style_guide
    if logo_group is not None:
        brand.logo = logo_group

    brand.save()
    return True, None


# ── Views ──────────────────────────────────────────────────────────────────

@login_required
def brand_detail(request):
    brand, _ = Brand.objects.get_or_create(user=request.user)
    edit_mode = request.GET.get('mode') == 'edit'

    if request.method == 'POST':
        form = BrandForm(request.POST, instance=brand, user=request.user)
        if form.is_valid():
            form.save()
            return redirect('brand:brand_detail')
        else:
            edit_mode = True
    else:
        form = BrandForm(instance=brand, user=request.user)

    # Preview URL and image ID for the logo field (reflects current form value, not just saved brand).
    logo_preview_url = ''
    logo_image_id = ''
    logo_value = form['logo'].value()
    if logo_value:
        try:
            group = ImageGroup.objects.prefetch_related('images').get(pk=logo_value)
            first_img = group.images.first()
            if first_img:
                logo_preview_url = first_img.url
                logo_image_id = str(first_img.pk)
        except (ImageGroup.DoesNotExist, ValueError):
            pass

    return render(request, 'brand/brand_detail.html', {
        'brand': brand,
        'form': form,
        'edit_mode': edit_mode,
        'logo_preview_url': logo_preview_url,
        'logo_image_id': logo_image_id,
    })


@login_required
def brand_scrape_modal(request):
    brand, _ = Brand.objects.get_or_create(user=request.user)
    initial_url = brand.website_url or ''

    if request.method == 'POST':
        form = ScrapeURLForm(request.POST)
        if form.is_valid():
            url = form.cleaned_data['url']
            success, error = _scrape_brand_data(request.user, url)
            if success:
                response = _accept_layer_response()
                response['X-Up-Events'] = '[{"type":"brand:scraped"}]'
                return response
            return render(request, 'brand/scrape_modal.html', {
                'form': form,
                'error': error,
            })
    else:
        form = ScrapeURLForm(initial={'url': initial_url})

    return render(request, 'brand/scrape_modal.html', {'form': form})


@login_required
def brand_onboarding(request):
    if request.method == 'POST':
        form = ScrapeURLForm(request.POST)
        if form.is_valid():
            url = form.cleaned_data['url']
            success, error = _scrape_brand_data(request.user, url)
            if success:
                return redirect('/')
            return render(request, 'brand/onboarding.html', {
                'form': form,
                'error': error,
            })
    else:
        form = ScrapeURLForm()

    return render(request, 'brand/onboarding.html', {'form': form})
