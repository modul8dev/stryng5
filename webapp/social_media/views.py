import json
import logging

from django.contrib.auth.decorators import login_required
from django.forms import inlineformset_factory
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from credits.constants import IMAGE_GENERATION_COST
from credits.models import available_credits, spend_credits

from brand.models import Brand
from media_library.models import Image, ImageGroup
from services.ai_services import suggest_topic, generate_post_text, generate_post_image, edit_text
from .forms import (
    SharedMediaFormSet,
    SocialMediaPostForm,
    SocialMediaPostPlatformForm,
)
from .models import (
    PLATFORM_CHOICES,
    SocialMediaPost,
    SocialMediaPostPlatform,
    SocialMediaPostSeedImage,
    SocialMediaPlatformMedia,
)
from .publisher import publish_post
from .tasks import publish_post_task


def _accept_layer_response():
    return HttpResponse(status=204)


def _build_image_groups_data(project):
    groups = ImageGroup.objects.filter(project=project).prefetch_related('images')
    return [
        {
            'id': g.id,
            'title': g.title,
            'images': [{'id': img.id, 'url': img.url} for img in g.images.all()],
        }
        for g in groups
    ]


def _save_platform_override_media(request, post):
    raw = request.POST.get('platform_override_media_json', '{}')
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return
    for platform_variant in post.platforms.all():
        images_data = data.get(platform_variant.platform)
        if images_data is None:
            continue
        platform_variant.override_media.all().delete()
        for sort_order, item in enumerate(images_data):
            image_id = item.get('image_id')
            if image_id:
                SocialMediaPlatformMedia.objects.create(
                    platform_variant=platform_variant,
                    image_id=image_id,
                    sort_order=sort_order,
                )


def _save_seed_images(request, post):
    raw = request.POST.get('seed_images_json', '[]')
    try:
        image_ids = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return
    post.seed_images.all().delete()
    for sort_order, image_id in enumerate(image_ids):
        if image_id:
            SocialMediaPostSeedImage.objects.create(
                post=post,
                image_id=image_id,
                sort_order=sort_order,
            )


def _get_platform_label(key):
    return dict(PLATFORM_CHOICES).get(key, key)


def _make_platform_formset(extra=0):
    return inlineformset_factory(
        SocialMediaPost,
        SocialMediaPostPlatform,
        form=SocialMediaPostPlatformForm,
        extra=extra,
        can_delete=False,
    )


@login_required
def post_list(request):
    posts = list(
        SocialMediaPost.objects.filter(project=request.project)
        .prefetch_related('platforms', 'shared_media__image')
    )
    for post in posts:
        all_media = list(post.shared_media.all())
        post.preview_media = all_media[:3]
        post.extra_media_count = max(0, len(all_media) - 3)
    return render(request, 'social_media/post_list.html', {'posts': posts})


@login_required
def post_create(request):
    enabled_platforms = request.project.get_enabled_platforms()
    user_images = Image.objects.filter(image_group__project=request.project).select_related('image_group')

    if request.method == 'POST':
        form = SocialMediaPostForm(request.POST)
        PlatformFormSet = _make_platform_formset(extra=len(enabled_platforms))
        platform_formset = PlatformFormSet(request.POST, prefix='platform', instance=SocialMediaPost())
        media_formset = SharedMediaFormSet(request.POST, prefix='media', instance=SocialMediaPost())
        if form.is_valid() and platform_formset.is_valid() and media_formset.is_valid():
            post = form.save(commit=False)
            post.user = request.user
            post.project = request.project
            if not post.title:
                post.title = 'Untitled'
            post.status = 'scheduled' if request.POST.get('action') == 'schedule' and post.scheduled_at else 'draft'
            post.save()
            platform_formset.instance = post
            platform_formset.save()
            media_formset.instance = post
            media_formset.save()
            _save_platform_override_media(request, post)
            _save_seed_images(request, post)
            return _accept_layer_response()
    else:
        form = SocialMediaPostForm()
        initial_platforms = [{'platform': p} for p in enabled_platforms]
        PlatformFormSet = _make_platform_formset(extra=len(enabled_platforms))
        platform_formset = PlatformFormSet(
            prefix='platform',
            instance=SocialMediaPost(),
            initial=initial_platforms,
        )
        media_formset = SharedMediaFormSet(prefix='media', instance=SocialMediaPost())

    # Adjust image queryset on media forms
    for mf in media_formset.forms:
        mf.fields['image'].queryset = user_images

    platform_labels = {p: _get_platform_label(p) for p in enabled_platforms}
    brand = _get_project_brand(request.project)

    # Support prefill from query params (used by inspiration cards)
    prefill_topic = request.GET.get('topic', '')
    prefill_mode = request.GET.get('mode', '')
    prefill_seed_image_ids_raw = request.GET.get('seed_image_ids', '')
    prefill_seed_images = []
    if prefill_seed_image_ids_raw:
        try:
            id_list = [int(x) for x in prefill_seed_image_ids_raw.split(',') if x.strip()]
            prefill_seed_images = [
                {'image_id': img.id, 'url': img.url}
                for img in Image.objects.filter(id__in=id_list, image_group__project=request.project)
            ]
        except (ValueError, TypeError):
            pass

    return render(request, 'social_media/post_form.html', {
        'form': form,
        'platform_formset': platform_formset,
        'media_formset': media_formset,
        'enabled_platforms': enabled_platforms,
        'platform_labels': platform_labels,
        'user_images': user_images,
        'selected_shared_media': [],
        'selected_platform_media': {},
        'selected_seed_images': prefill_seed_images if prefill_seed_images else [],
        'brand': brand,
        'is_edit': False,
        'prefill_topic': prefill_topic,
        'prefill_mode': prefill_mode,
    })


@login_required
def post_edit(request, pk):
    post = get_object_or_404(SocialMediaPost, pk=pk, project=request.project)
    user_images = Image.objects.filter(image_group__project=request.project).select_related('image_group')

    PlatformFormSet = _make_platform_formset(extra=0)
    if request.method == 'POST':
        form = SocialMediaPostForm(request.POST, instance=post)
        platform_formset = PlatformFormSet(request.POST, instance=post, prefix='platform')
        media_formset = SharedMediaFormSet(request.POST, instance=post, prefix='media')
        if form.is_valid() and platform_formset.is_valid() and media_formset.is_valid():
            updated_post = form.save(commit=False)
            if not updated_post.title:
                updated_post.title = 'Untitled'
            if request.POST.get('action') == 'schedule' and updated_post.scheduled_at:
                updated_post.status = 'scheduled'
            updated_post.save()
            platform_formset.save()
            media_formset.save()
            _save_platform_override_media(request, post)
            _save_seed_images(request, post)
            return _accept_layer_response()
    else:
        form = SocialMediaPostForm(instance=post)
        platform_formset = PlatformFormSet(instance=post, prefix='platform')
        media_formset = SharedMediaFormSet(instance=post, prefix='media')

    for mf in media_formset.forms:
        mf.fields['image'].queryset = user_images

    enabled_platforms = [p.platform for p in post.platforms.all()]
    platform_labels = {p: _get_platform_label(p) for p in enabled_platforms}

    selected_shared_media = [
        {'media_id': m.id, 'image_id': m.image_id, 'url': m.image.url}
        for m in post.shared_media.order_by('sort_order')
    ]
    platform_override_media = {}
    for pv in post.platforms.prefetch_related('override_media__image').all():
        platform_override_media[pv.platform] = [
            {'media_id': m.id, 'image_id': m.image_id, 'url': m.image.url}
            for m in pv.override_media.order_by('sort_order')
        ]

    selected_seed_images = [
        {'image_id': s.image_id, 'url': s.image.url}
        for s in post.seed_images.select_related('image').order_by('sort_order')
    ]

    return render(request, 'social_media/post_form.html', {
        'form': form,
        'platform_formset': platform_formset,
        'media_formset': media_formset,
        'enabled_platforms': enabled_platforms,
        'platform_labels': platform_labels,
        'user_images': user_images,
        'selected_shared_media': selected_shared_media,
        'selected_platform_media': platform_override_media,
        'selected_seed_images': selected_seed_images,
        'brand': _get_project_brand(request.project),
        'post': post,
        'is_edit': True,
    })



@login_required
@require_POST
def post_delete(request, pk):
    post = get_object_or_404(SocialMediaPost, pk=pk, project=request.project)
    post.delete()
    response = redirect(reverse('social_media:post_list'))
    response['X-Up-Events'] = '[{"type":"social_media:changed"}]'
    return response


logger = logging.getLogger(__name__)


def _get_project_brand(project):
    try:
        return Brand.objects.get(project=project)
    except Brand.DoesNotExist:
        return None


def _parse_json_body(request):
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return None


@login_required
@require_POST
def ai_suggest_topic(request):
    data = _parse_json_body(request)
    if not data:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    brand = _get_project_brand(request.project)
    if not brand:
        return JsonResponse({'error': 'Brand not configured'}, status=400)

    seed_image_ids = data.get('seed_image_ids', [])
    seed_images = list(
        Image.objects.filter(
            id__in=seed_image_ids,
            image_group__project=request.project,
        )
    ) if seed_image_ids else []

    try:
        topics = suggest_topic(brand, seed_images)
        return JsonResponse({'topics': topics})
    except Exception:
        logger.exception('Failed to suggest topic')
        return JsonResponse({'error': 'Failed to suggest topic'}, status=500)


@login_required
@require_POST
def ai_generate(request):
    data = _parse_json_body(request)
    if not data:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    brand = _get_project_brand(request.project)
    if not brand:
        return JsonResponse({'error': 'Brand not configured'}, status=400)

    topic = data.get('topic', '')
    post_type = data.get('post_type', '')
    platforms = data.get('platforms', [])
    seed_image_ids = data.get('seed_image_ids', [])

    seed_images = list(
        Image.objects.filter(
            id__in=seed_image_ids,
            image_group__project=request.project,
        )
    ) if seed_image_ids else []

    # Check credits before image generation
    if available_credits(request.user) < IMAGE_GENERATION_COST:
        return JsonResponse(
            {'error': 'Insufficient credits', 'credits_required': IMAGE_GENERATION_COST},
            status=402,
        )

    result = {}

    try:
        result['text'] = generate_post_text(brand, topic, post_type, seed_images, platforms)
    except Exception:
        logger.exception('Failed to generate post text')
        return JsonResponse({'error': 'Failed to generate text'}, status=500)

    try:
        image = generate_post_image(brand, topic, post_type, seed_images, request.user, project=request.project)
        if image:
            spend_credits(request.user, IMAGE_GENERATION_COST, 'Post image generation')
            result['image'] = {'id': image.id, 'url': image.url}
    except Exception:
        logger.exception('Failed to generate image (text was generated successfully)')
        # Non-fatal: text was already generated

    return JsonResponse(result)


@login_required
@require_POST
def ai_edit_text(request):
    data = _parse_json_body(request)
    if not data:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    brand = _get_project_brand(request.project)
    if not brand:
        return JsonResponse({'error': 'Brand not configured'}, status=400)

    action = data.get('action', '')
    text = data.get('text', '')
    platform = data.get('platform')
    instruction = data.get('instruction')
    system_prompt = data.get('system_prompt') or None
    # field_name and result_mode accepted for forward-compatibility; not yet used server-side
    _ = data.get('field_name')
    _ = data.get('result_mode')

    if not action or not text:
        return JsonResponse({'error': 'action and text are required'}, status=400)

    try:
        edited = edit_text(action, text, brand, platform=platform, instruction=instruction, system_prompt_key=system_prompt)
        return JsonResponse({'text': edited})
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception:
        logger.exception('Failed to edit text')
        return JsonResponse({'error': 'Failed to edit text'}, status=500)

@login_required
@require_POST
def post_publish(request, pk):
    """Enqueue an async task to publish the post to all connected platforms."""
    post = get_object_or_404(SocialMediaPost, pk=pk, project=request.project)
    base_url = request.build_absolute_uri('/').rstrip('/')
    from django_q.tasks import async_task
    async_task('social_media.tasks.publish_post_task', post.pk, base_url)
    return JsonResponse({'queued': True})


@login_required
def post_publish_info(request, pk):
    """Return publish info fragment for the given post (shown in modal)."""
    post = get_object_or_404(SocialMediaPost, pk=pk, project=request.project)
    platforms = post.platforms.filter(is_enabled=True)
    return render(request, 'social_media/post_publish_info.html', {
        'post': post,
        'platforms': platforms,
    })


@login_required
@require_POST
def post_unschedule(request, pk):
    """Return a post from scheduled back to draft status."""
    post = get_object_or_404(SocialMediaPost, pk=pk, project=request.project)
    post.status = 'draft'
    post.scheduled_at = None
    post.save(update_fields=['status', 'scheduled_at'])
    return JsonResponse({'status': 'draft'})


@login_required
@require_POST
def post_schedule(request, pk):
    """Validate datetime and schedule a post."""
    from django.utils import timezone
    from datetime import datetime as dt_class

    post = get_object_or_404(SocialMediaPost, pk=pk, project=request.project)
    scheduled_at_str = request.POST.get('scheduled_at', '').strip()

    if not scheduled_at_str:
        return JsonResponse({'error': 'Please enter a date and time.'}, status=400)
    try:
        scheduled_at = dt_class.fromisoformat(scheduled_at_str)
        if timezone.is_naive(scheduled_at):
            scheduled_at = timezone.make_aware(scheduled_at)
        if scheduled_at <= timezone.now():
            return JsonResponse({'error': 'Scheduled time must be in the future.'}, status=400)
        post.scheduled_at = scheduled_at
        post.status = 'scheduled'
        post.save(update_fields=['scheduled_at', 'status'])
        return JsonResponse({
            'status': 'scheduled',
            'scheduled_at': post.scheduled_at.isoformat(),
        })
    except ValueError:
        return JsonResponse({'error': 'Invalid date/time format.'}, status=400)


@login_required
def post_publish_panel(request, pk):
    """Render the publish panel fragment (opened as Unpoly modal)."""
    post = get_object_or_404(SocialMediaPost, pk=pk, project=request.project)
    platforms = post.platforms.filter(is_enabled=True).order_by('platform')
    return render(request, 'social_media/post_publish_panel.html', {
        'post': post,
        'platforms': platforms,
    })