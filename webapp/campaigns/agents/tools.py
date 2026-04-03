import json
from dataclasses import dataclass

from django.conf import settings
from pydantic import BaseModel
from agents import function_tool, RunContextWrapper

from brand.models import Brand
from credits.constants import IMAGE_GENERATION_COST
from credits.models import available_credits, spend_credits
from media_library.models import Image, ImageGroup
from social_media.ai_services import generate_post_image
from social_media.models import (
    PLATFORM_CHAR_LIMITS,
    SocialMediaPost,
    SocialMediaPostMedia,
    SocialMediaPostPlatform,
)


@dataclass
class AgentContext:
    user_id: int
    project_id: int
    brand_id: int | None
    conversation_id: int


def _make_absolute_url(url: str) -> str:
    """Convert a relative media URL to a full absolute URL using settings.SITE_URL."""
    if not url:
        return url
    if url.startswith('http://') or url.startswith('https://'):
        return url
    site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').rstrip('/')
    return f'{site_url}{url}'


def _get_brand(ctx: RunContextWrapper[AgentContext]):
    if ctx.context.brand_id:
        return Brand.objects.filter(pk=ctx.context.brand_id).first()
    return None


@function_tool
def get_brand_info(ctx: RunContextWrapper[AgentContext]) -> str:
    """Get the brand information including name, summary, language, and style guide."""
    brand = _get_brand(ctx)
    if not brand:
        return json.dumps({'error': 'No brand configured for this project.'})
    return json.dumps({
        'name': brand.name or '',
        'summary': brand.summary or '',
        'language': brand.language or 'English',
        'style_guide': brand.style_guide or '',
    })


@function_tool
def get_enabled_platforms(ctx: RunContextWrapper[AgentContext]) -> str:
    """Get the list of enabled social media platforms for this project, along with their character limits."""
    from projects.models import Project
    project = Project.objects.filter(pk=ctx.context.project_id).first()
    if not project:
        return json.dumps({'error': 'Project not found.'})
    platforms = project.get_enabled_platforms()
    return json.dumps({
        'platforms': platforms,
        'char_limits': {p: PLATFORM_CHAR_LIMITS.get(p, 5000) for p in platforms},
    })


@function_tool
def describe_image(ctx: RunContextWrapper[AgentContext], image_id: int, image_url: str) -> str:
    """Analyze the visual content of a single image using AI vision. Returns a description suitable for marketing use."""
    from openai import OpenAI
    client = OpenAI()
    try:
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'text',
                            'text': (
                                'Describe this image for social media marketing. Include: '
                                'what products/subjects are shown, colors, mood, composition style, '
                                'and how it could be used in a marketing campaign. Be concise (2-3 sentences).'
                            ),
                        },
                        {
                            'type': 'image_url',
                            'image_url': {'url': image_url, 'detail': 'low'},
                        },
                    ],
                }
            ],
            max_tokens=200,
        )
        description = response.choices[0].message.content or ''
        return json.dumps({'image_id': image_id, 'url': image_url, 'description': description})
    except Exception as e:
        return json.dumps({
            'image_id': image_id,
            'url': image_url,
            'description': f'Could not analyze image (may be internally hosted): {str(e)[:80]}',
        })


@function_tool
def list_image_groups(ctx: RunContextWrapper[AgentContext]) -> str:
    """List available image groups in the media library with their image counts. Use this to understand what images are available before selecting."""
    groups = ImageGroup.objects.filter(
        project_id=ctx.context.project_id,
        type=ImageGroup.GroupType.PRODUCT
    ).prefetch_related('images')
    result = []
    for group in groups[:20]:
        images = list(group.images.all()[:10])
        result.append({
            'id': group.id,
            'title': group.title,
            'description': group.description or '',
            'type': group.type,
            'image_count': group.images.count(),
            'images': [
                {'id': img.id, 'url': _make_absolute_url(img.url)}
                for img in images
            ],
        })
    return json.dumps(result)


@function_tool
def search_images(ctx: RunContextWrapper[AgentContext], query: str) -> str:
    """Search for images in the media library by group title or description. Returns matching images with their IDs and absolute URLs."""
    from django.db.models import Q
    groups = ImageGroup.objects.filter(
        Q(title__icontains=query) | Q(description__icontains=query),
        project_id=ctx.context.project_id,
    ).prefetch_related('images')[:10]
    results = []
    for group in groups:
        for img in group.images.all()[:5]:
            results.append({
                'id': img.id,
                'group_title': group.title,
                'group_description': group.description or '',
                'url': _make_absolute_url(img.url),
            })
    if not results:
        return json.dumps({'message': 'No images found matching your query.', 'results': []})
    return json.dumps(results)


@function_tool
def search_unsplash(ctx: RunContextWrapper[AgentContext], query: str, count: int = 5) -> str:
    """Search Unsplash for free stock photos matching the query. Saves results to the media library as external references and returns image IDs and full URLs suitable for use as seed images."""
    import requests as http_requests
    from django.contrib.auth import get_user_model

    access_key = getattr(settings, 'UNSPLASH_ACCESS_KEY', '')
    if not access_key:
        return json.dumps({'error': 'Unsplash API key not configured. Set UNSPLASH_ACCESS_KEY in environment.'})

    try:
        resp = http_requests.get(
            'https://api.unsplash.com/search/photos',
            params={'query': query, 'per_page': min(max(count, 1), 10), 'client_id': access_key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return json.dumps({'error': f'Unsplash search failed: {str(e)[:120]}'})

    items = data.get('results', [])
    if not items:
        return json.dumps({'message': 'No Unsplash results found for this query.', 'results': []})

    User = get_user_model()
    user = User.objects.get(pk=ctx.context.user_id)

    group, _ = ImageGroup.objects.get_or_create(
        project_id=ctx.context.project_id,
        title='Unsplash References',
        defaults={
            'user': user,
            'type': ImageGroup.GroupType.MANUAL,
            'description': 'Images imported from Unsplash as campaign references and seed images.',
        },
    )

    results = []
    for item in items:
        img_url = item['urls'].get('regular') or item['urls'].get('full', '')
        if not img_url:
            continue
        img_obj, _ = Image.objects.get_or_create(
            image_group=group,
            external_url=img_url,
            defaults={'image_type': Image.ImageType.MANUAL},
        )
        results.append({
            'id': img_obj.id,
            'url': img_url,
            'description': item.get('description') or item.get('alt_description') or query,
            'photographer': item.get('user', {}).get('name', ''),
        })

    return json.dumps({'results': results, 'source': 'unsplash'})


@function_tool
def generate_image(
    ctx: RunContextWrapper[AgentContext],
    prompt: str,
    seed_image_ids: list[int] | None = None,
) -> str:
    """Generate a new image using AI. Costs 1 credit. Provide a descriptive prompt for the image you want. Optionally reference seed_image_ids from the media library for style guidance."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.get(pk=ctx.context.user_id)

    credits = available_credits(user)
    if credits < IMAGE_GENERATION_COST:
        return json.dumps({
            'error': f'Insufficient credits. Need {IMAGE_GENERATION_COST}, have {credits}.',
        })

    brand = _get_brand(ctx)
    seed_images = []
    if seed_image_ids:
        seed_images = list(Image.objects.filter(
            pk__in=seed_image_ids,
            image_group__project_id=ctx.context.project_id,
        ))

    from projects.models import Project
    project = Project.objects.get(pk=ctx.context.project_id)

    image_obj = generate_post_image(
        brand=brand,
        topic=prompt,
        post_type='lifestyle',
        seed_images=seed_images,
        user=user,
        project=project,
    )
    if image_obj is None:
        return json.dumps({'error': 'Image generation failed.'})

    spend_credits(user, IMAGE_GENERATION_COST, 'campaign_image_generation')

    return json.dumps({
        'id': image_obj.id,
        'url': _make_absolute_url(image_obj.url),
        'message': 'Image generated successfully.',
    })


class PostData(BaseModel):
    title: str
    text: str
    topic: str = ''
    post_type: str = 'lifestyle'
    platforms: list[str] = []
    image_ids: list[int] = []


@function_tool
def create_posts(
    ctx: RunContextWrapper[AgentContext],
    posts: list[PostData],
) -> str:
    """Create social media posts from structured data. Returns the created post IDs."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.get(pk=ctx.context.user_id)

    created_ids = []
    for post_data in posts:
        post = SocialMediaPost.objects.create(
            user=user,
            project_id=ctx.context.project_id,
            title=post_data.title,
            shared_text=post_data.text,
            topic=post_data.topic,
            post_type=post_data.post_type,
            status='draft',
        )

        for platform_name in post_data.platforms:
            SocialMediaPostPlatform.objects.create(
                post=post,
                platform=platform_name,
                is_enabled=True,
                use_shared_text=True,
                use_shared_media=True,
            )

        for sort_order, img_id in enumerate(post_data.image_ids):
            if Image.objects.filter(pk=img_id).exists():
                SocialMediaPostMedia.objects.create(
                    post=post,
                    image_id=img_id,
                    sort_order=sort_order,
                )

        created_ids.append(post.id)

    return json.dumps({
        'created_post_ids': created_ids,
        'count': len(created_ids),
        'message': f'Successfully created {len(created_ids)} post(s).',
    })
