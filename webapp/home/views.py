import logging
import os
import uuid

import requests as http_requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_q.tasks import async_task

from accounts.forms import ProfileForm
from brand.models import Brand
from credits.models import CreditGrant, available_credits
from credits.views import get_subscription_info
from media_library.models import Media, MediaGroup
from social_media.models import SocialMediaPost

UNSPLASH_ACCESS_KEY = os.environ.get('UNSPLASH_ACCESS_KEY', '')

logger = logging.getLogger(__name__)


@login_required
def home(request):
    now = timezone.now()
    # Monday of the current week
    week_start = now - timezone.timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timezone.timedelta(days=7)

    drafts = (
        SocialMediaPost.objects.filter(project=request.project, status='draft')
        .prefetch_related('shared_media__media')
        .order_by('-updated_at')[:4]
    )

    scheduled_posts = (
        SocialMediaPost.objects.filter(
            project=request.project,
            status='scheduled',
            scheduled_at__gte=week_start,
            scheduled_at__lt=week_end,
        )
        .prefetch_related('platforms')
        .order_by('scheduled_at')
    )

    try:
        brand = Brand.objects.get(project=request.project)
        has_brand = brand.has_data
    except Brand.DoesNotExist:
        brand = None
        has_brand = False

    has_products = MediaGroup.objects.filter(project=request.project, type=MediaGroup.GroupType.PRODUCT).exists()

    media_groups = (
        MediaGroup.objects.filter(project=request.project, type=MediaGroup.GroupType.MANUAL)
        .prefetch_related('media_items')
        .order_by('-created_at')[:6]
    )

    is_scraping = brand is not None and brand.processing_status == Brand.ProcessingStatus.SCRAPING
    is_importing = bool(request.project and request.project.product_import_in_progress)

    return render(request, "home/home.html", {
        'drafts': drafts,
        'scheduled_posts': scheduled_posts,
        'brand': brand,
        'has_brand': has_brand,
        'has_products': has_products,
        'is_scraping': is_scraping,
        'is_importing': is_importing,
        'media_groups': media_groups,
        'auto_provision_project_id': request.session.pop('auto_provision_project_id', None),
    })


@login_required
def inspiration_cards(request):
    cache_key = f'inspiration_{uuid.uuid4().hex}'
    async_task(
        'home.tasks.generate_inspiration_task',
        request.project.id,
        request.user.id,
        cache_key,
    )
    return render(request, 'home/_inspiration_loading.html', {'cache_key': cache_key})


@login_required
def inspiration_cards_result(request):
    cache_key = request.GET.get('key', '')
    if not cache_key.startswith('inspiration_') or len(cache_key) > 50:
        return render(request, 'home/_inspiration_cards.html', {'cards': []})

    cached = cache.get(cache_key)
    if not cached or cached.get('project_id') != request.project.id:
        return render(request, 'home/_inspiration_cards.html', {'cards': []})

    raw_cards = cached.get('cards', [])
    media_ids = [c['media'] for c in raw_cards if c['media']]
    media_by_id = {m.id: m for m in Media.objects.filter(id__in=media_ids)}

    cards = []
    for c in raw_cards:
        cards.append({
            'group': {'title': c['group_title']},
            'media': media_by_id.get(c['media']),
            'topic': c['topic'],
            'seed_media_ids': c['seed_media_ids'],
        })

    return render(request, 'home/_inspiration_cards.html', {'cards': cards})

@login_required
def settings(request):
    profile_form = ProfileForm(instance=request.user)

    if request.method == "POST":
        profile_form = ProfileForm(request.POST, instance=request.user)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, "Profile updated.")
            return redirect("settings")

    now = timezone.now()
    active_grants = list(
        CreditGrant.objects.filter(user=request.user, expires_at__gt=now).order_by('expires_at')
    )
    total_credits = sum(g.remaining for g in active_grants)
    subscription = get_subscription_info(request.user)

    return render(request, "home/settings.html", {
        "form": profile_form,
        "active_grants": active_grants,
        "total_credits": total_credits,
        "subscription": subscription,
    })


@login_required
def unsplash_photos(request):
    photos = []
    error = None
    search_term = None
    if UNSPLASH_ACCESS_KEY:
        try:
            try:
                brand = Brand.objects.get(project=request.project)
                if brand.has_data:
                    from services.ai_services import get_unsplash_search_term
                    search_term = get_unsplash_search_term(brand)
            except Brand.DoesNotExist:
                pass

            if search_term:
                resp = http_requests.get(
                    'https://api.unsplash.com/search/photos',
                    params={'query': search_term, 'per_page': 6},
                    headers={'Authorization': f'Client-ID {UNSPLASH_ACCESS_KEY}'},
                    timeout=10,
                )
                resp.raise_for_status()
                photos = resp.json().get('results', [])
            else:
                resp = http_requests.get(
                    'https://api.unsplash.com/photos/random',
                    params={'count': 6},
                    headers={'Authorization': f'Client-ID {UNSPLASH_ACCESS_KEY}'},
                    timeout=10,
                )
                resp.raise_for_status()
                photos = resp.json()
        except Exception:
            logger.exception('Failed to fetch Unsplash photos')
            error = 'Could not load photos from Unsplash.'
    return render(request, 'home/_unsplash_inspiration.html', {'photos': photos, 'error': error, 'search_term': search_term})


@login_required
@require_POST
def save_unsplash_media(request):
    photo_url = request.POST.get('photo_url', '').strip()
    photo_id = request.POST.get('photo_id', '').strip()
    title = request.POST.get('title', '').strip() or 'Unsplash Photo'

    if photo_url and photo_id:
        group = MediaGroup.objects.create(
            user=request.user,
            project=request.project,
            title=title,
            type=MediaGroup.GroupType.MANUAL,
        )
        Media.objects.create(media_group=group, external_url=photo_url)

    return render(request, 'home/_unsplash_save_button.html', {
        'saved': True,
        'photo_id': photo_id,
    })
