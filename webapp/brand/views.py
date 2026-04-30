import os
from urllib.parse import urljoin, urlparse

import requests as http_requests
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from media_library.models import Image, ImageGroup
from media_library.views import _detect_and_import_products, _import_url_images

from media_library.models import ImageGroup
from .forms import BrandForm, ScrapeURLForm
from .models import Brand


# ── Unpoly modal helper ─────────────────────────────────────────────────────

def _accept_layer_response():
    response = HttpResponse(status=204)
    response['X-Up-Accept-Layer'] = 'null'
    return response


# ── Brand scraping ──────────────────────────────────────────────────────────


def _create_logo_image_group(user, project, logo_url, brand_name):
    """Create an ImageGroup containing the logo URL. Returns the group or None."""
    try:
        group = ImageGroup.objects.create(
            user=user,
            project=project,
            title=f'{brand_name} Logo' if brand_name else 'Brand Logo',
            type=ImageGroup.GroupType.MANUAL,
        )
        Image.objects.create(image_group=group, external_url=logo_url)
        return group
    except Exception:
        return None


def _scrape_brand_data(user, project, url):
    """
    4-phase brand scraping:
      1. Map the site to discover all URLs (Firecrawl /map).
      2. LLM selects the 5-7 pages most relevant to brand identity.
      3. Batch-scrape those pages for markdown content.
      4. Feed combined markdown into OpenAI for structured brand extraction.
    Also imports website images and handles Shopify/WooCommerce product discovery.
    Returns (success: bool, error: str | None).
    """
    firecrawl_key = os.environ.get('FIRECRAWL_API_KEY', '')
    if not firecrawl_key:
        return False, 'FIRECRAWL_API_KEY is not configured.'

    openai_key = os.environ.get('OPENAI_API_KEY', '')
    if not openai_key:
        return False, 'OPENAI_API_KEY is not configured.'

    from firecrawl import Firecrawl
    from services.ai_services import extract_brand_data, select_brand_urls

    fc = Firecrawl(api_key=firecrawl_key)

    # ── Phase 1: Map website to discover all URLs ────────────────────────────
    all_urls = []
    try:
        map_result = fc.map(url, limit=50)
        raw_links = getattr(map_result, 'links', None) or []
        for item in raw_links:
            if isinstance(item, dict):
                u = item.get('url', '')
            else:
                u = getattr(item, 'url', str(item))
            if u:
                all_urls.append(u)
    except Exception:
        pass  # Phase 1 failure is non-fatal; fall back to homepage only

    # ── Phase 2: LLM selects most brand-relevant URLs ────────────────────────
    selected_urls = []
    if len(all_urls) > 1:
        try:
            selected_urls = select_brand_urls(all_urls, url)
        except Exception:
            pass

    # Always ensure the homepage is included; deduplicate
    if url not in selected_urls:
        selected_urls.insert(0, url)
    # Limit to 7 pages to control cost
    selected_urls = selected_urls[:7]

    # ── Fetch logo and branding design tokens from homepage ──────────────────
    logo_url = None
    branding_primary_color = ''
    branding_secondary_color = ''
    branding_fonts = ''
    try:
        homepage_result = fc.scrape(url, formats=['branding'])
        branding = getattr(homepage_result, 'branding', None)
        if branding:
            def _bg(obj, key, default=None):
                """Safe getter for both dict and object (Pydantic) branding nodes."""
                if obj is None:
                    return default
                return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

            # Logo
            images = _bg(branding, 'images')
            if images:
                logo_url = _bg(images, 'logo')

            # Colors
            colors = _bg(branding, 'colors')
            if colors:
                branding_primary_color = (_bg(colors, 'primary') or '').strip()
                branding_secondary_color = (_bg(colors, 'secondary') or '').strip()

            # Fonts — prefer typography.fontFamilies, fall back to fonts list
            typography = _bg(branding, 'typography')
            font_families = _bg(typography, 'fontFamilies') if typography else None
            if font_families:
                seen, unique = set(), []
                for k in ('primary', 'heading', 'body', 'code'):
                    f = _bg(font_families, k)
                    if f and f not in seen:
                        seen.add(f)
                        unique.append(f)
                branding_fonts = ', '.join(unique)

            if not branding_fonts:
                fonts_list = _bg(branding, 'fonts') or []
                names = [
                    (_bg(f, 'family') if isinstance(f, dict) else getattr(f, 'family', ''))
                    for f in fonts_list
                ]
                branding_fonts = ', '.join(n for n in names if n)
    except Exception:
        pass

    # ── Phase 3: Batch-scrape the selected pages for markdown ────────────────
    combined_markdown = ''
    try:
        batch_result = fc.batch_scrape(
            selected_urls,
            formats=['markdown'],
            only_main_content=True,
            poll_interval=5,
            wait_timeout=120,
        )
        pages = getattr(batch_result, 'data', None) or []
        combined_markdown = '\n\n---\n\n'.join(
            (getattr(p, 'markdown', '') or '')
            for p in pages
            if getattr(p, 'markdown', None)
        )
    except Exception as exc:
        # Fall back to a single scrape of the homepage
        try:
            fallback = fc.scrape(url, formats=['markdown'])
            combined_markdown = getattr(fallback, 'markdown', '') or ''
        except Exception as exc2:
            return False, f'Failed to scrape page: {exc2}'

    if not combined_markdown:
        return False, 'Could not retrieve page content for analysis.'

    # ── Phase 4: Structured brand extraction via OpenAI ──────────────────────
    try:
        extracted = extract_brand_data(combined_markdown)
    except Exception as exc:
        return False, f'Failed to extract brand data: {exc}'

    brand_name = extracted.get('name', '').strip()
    brand_summary = extracted.get('summary', '').strip()
    brand_language = extracted.get('language', '').strip()
    brand_style_guide = extracted.get('style_guide', '').strip()
    brand_tone_of_voice = extracted.get('tone_of_voice', '').strip()
    brand_target_audience = extracted.get('target_audience', '').strip()
    brand_fonts = extracted.get('fonts', '').strip()
    brand_primary_color = extracted.get('primary_color', '').strip()
    brand_secondary_color = extracted.get('secondary_color', '').strip()

    # Branding tokens (from CSS/design system) take precedence over LLM inference
    if branding_fonts:
        brand_fonts = branding_fonts
    if branding_primary_color:
        brand_primary_color = branding_primary_color
    if branding_secondary_color:
        brand_secondary_color = branding_secondary_color

    # ── Create logo ImageGroup ───────────────────────────────────────────────
    logo_group = None
    if logo_url:
        logo_group = _create_logo_image_group(user, project, logo_url, brand_name)

    # ── Save brand data ──────────────────────────────────────────────────────
    brand, _ = Brand.objects.get_or_create(project=project, defaults={'user': user})
    brand.website_url = url
    brand.name = brand_name
    brand.summary = brand_summary
    brand.language = brand_language
    brand.style_guide = brand_style_guide
    brand.tone_of_voice = brand_tone_of_voice
    brand.target_audience = brand_target_audience
    brand.fonts = brand_fonts
    brand.primary_color = brand_primary_color
    brand.secondary_color = brand_secondary_color
    if logo_group is not None:
        brand.logo = logo_group

    brand.save()
    return True, None


# ── Views ──────────────────────────────────────────────────────────────────

@login_required
def brand_detail(request):
    brand, _ = Brand.objects.get_or_create(project=request.project, defaults={'user': request.user})
    edit_mode = request.GET.get('mode') == 'edit'

    if request.method == 'POST':
        form = BrandForm(request.POST, instance=brand, project=request.project)
        if form.is_valid():
            form.save()
            return redirect('brand:brand_detail')
        else:
            edit_mode = True
    else:
        form = BrandForm(instance=brand, project=request.project)

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
    brand, _ = Brand.objects.get_or_create(project=request.project, defaults={'user': request.user})
    initial_url = brand.website_url or ''

    if request.method == 'POST':
        form = ScrapeURLForm(request.POST)
        if form.is_valid():
            if brand.processing_status == Brand.ProcessingStatus.SCRAPING:
                return render(request, 'brand/scrape_modal.html', {
                    'form': form,
                    'brand': brand,
                    'already_scraping': True,
                })
            url = form.cleaned_data['url']
            Brand.objects.filter(pk=brand.pk).update(
                processing_status=Brand.ProcessingStatus.SCRAPING,
                scrape_error='',
                website_url=url,
            )
            from django_q.tasks import async_task
            from .tasks import scrape_brand_task
            async_task(
                scrape_brand_task, brand.pk, url,
                user_id=request.user.id
            )
            response = render(request, 'brand/scrape_modal.html', {
                'form': form,
                'brand': brand,
                'scraping_started': True,
            })
            response['X-Up-Events'] = '[{"type":"brand:scrape_started"}]'
            return response
    else:
        form = ScrapeURLForm(initial={'url': initial_url})

    return render(request, 'brand/scrape_modal.html', {'form': form, 'brand': brand})


@login_required
def brand_onboarding(request):
    if request.method == 'POST':
        form = ScrapeURLForm(request.POST)
        if form.is_valid():
            url = form.cleaned_data['url']
            brand, _ = Brand.objects.get_or_create(project=request.project, defaults={'user': request.user})
            if brand.processing_status == Brand.ProcessingStatus.SCRAPING:
                return render(request, 'brand/onboarding.html', {
                    'form': form,
                    'already_scraping': True,
                })
            Brand.objects.filter(pk=brand.pk).update(
                processing_status=Brand.ProcessingStatus.SCRAPING,
                scrape_error='',
                website_url=url,
            )
            from django_q.tasks import async_task
            from .tasks import scrape_brand_task
            async_task(
                scrape_brand_task, brand.pk, url,
                user_id=request.user.id,
                q_options={'task_name': 'scrape_brand'},
            )
            return render(request, 'brand/onboarding.html', {
                'form': form,
                'scraping_started': True,
                'project_id': request.project.pk,
            })
    else:
        form = ScrapeURLForm()

    return render(request, 'brand/onboarding.html', {'form': form})
