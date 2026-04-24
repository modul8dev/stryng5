"""
Social media publishing service.

Each platform function publishes one SocialMediaPostPlatform variant
using its connected IntegrationConnection credentials.

The central `publish_post` function checks which platforms have active
connections and dispatches to the appropriate publisher.
"""

import logging
import mimetypes

import requests as http_requests
from django.utils import timezone

from integrations.models import IntegrationConnection

logger = logging.getLogger(__name__)

LINKEDIN_API_BASE = 'https://api.linkedin.com'
GRAPH_API_BASE = 'https://graph.facebook.com/v22.0'
IG_GRAPH_BASE = 'https://graph.instagram.com/v22.0'
TWITTER_API_BASE = 'https://api.twitter.com/2'
TWITTER_UPLOAD_BASE = 'https://upload.twitter.com/1.1'


# ─── Image helpers ────────────────────────────────────────────────────────────


def _get_image_bytes_and_type(image):
    """Return (bytes_data, content_type) for a media_library.Image instance."""
    if image.image:
        # Local stored file — read from storage
        with image.image.open('rb') as f:
            data = f.read()
        mime, _ = mimetypes.guess_type(image.image.name)
        return data, mime or 'image/jpeg'
    # External URL — download it
    resp = http_requests.get(image.external_url, timeout=30)
    resp.raise_for_status()
    ct = resp.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip()
    return resp.content, ct


def _get_absolute_image_url(image, base_url):
    """
    Return a publicly accessible URL for an image.
    For local Django-stored images the base_url (e.g. https://example.com)
    is prepended to the storage-relative URL.
    """
    if image.external_url:
        return image.external_url
    return base_url.rstrip('/') + image.image.url


# ─── LinkedIn ────────────────────────────────────────────────────────────────


def publish_to_linkedin(platform_variant, connection, base_url=''):
    """Publish to LinkedIn using the REST Posts API (LinkedIn-Version 202411)."""
    token = connection.access_token
    member_id = connection.external_account_id
    author_urn = f'urn:li:person:{member_id}'
    text = platform_variant.get_effective_text()
    images = list(platform_variant.get_effective_media())

    auth_headers = {
        'Authorization': f'Bearer {token}',
        'LinkedIn-Version': '202411',
        'X-Restli-Protocol-Version': '2.0.0',
    }

    # Upload images and collect their URNs
    image_urns = []
    for media in images:
        image_data, content_type = _get_image_bytes_and_type(media.image)

        # Step 1 — initialize upload
        init_resp = http_requests.post(
            f'{LINKEDIN_API_BASE}/rest/images?action=initializeUpload',
            headers={**auth_headers, 'Content-Type': 'application/json'},
            json={'initializeUploadRequest': {'owner': author_urn}},
            timeout=30,
        )
        init_resp.raise_for_status()
        init_data = init_resp.json()
        upload_url = init_data['value']['uploadUrl']
        image_urn = init_data['value']['image']

        # Step 2 — upload binary
        put_resp = http_requests.put(
            upload_url,
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': content_type,
            },
            data=image_data,
            timeout=60,
        )
        put_resp.raise_for_status()
        image_urns.append(image_urn)

    # Build post payload
    payload = {
        'author': author_urn,
        'commentary': text,
        'visibility': 'PUBLIC',
        'distribution': {
            'feedDistribution': 'MAIN_FEED',
            'targetEntities': [],
            'thirdPartyDistributionChannels': [],
        },
        'lifecycleState': 'PUBLISHED',
        'isReshareDisabledByAuthor': False,
    }

    if len(image_urns) == 1:
        payload['content'] = {'media': {'id': image_urns[0], 'title': 'Image'}}
    elif len(image_urns) > 1:
        payload['content'] = {
            'multiImage': {
                'images': [
                    {'id': urn, 'altText': f'Image {i + 1}'}
                    for i, urn in enumerate(image_urns)
                ]
            }
        }

    post_resp = http_requests.post(
        f'{LINKEDIN_API_BASE}/rest/posts',
        headers={**auth_headers, 'Content-Type': 'application/json'},
        json=payload,
        timeout=30,
    )
    post_resp.raise_for_status()


# ─── X (Twitter) ─────────────────────────────────────────────────────────────


def publish_to_twitter(platform_variant, connection, base_url=''):
    """Publish to X (Twitter) using the v2 Tweets API."""
    token = connection.access_token
    text = platform_variant.get_effective_text()
    images = list(platform_variant.get_effective_media())

    auth_headers = {'Authorization': f'Bearer {token}'}

    # Upload media (v1.1 endpoint — still required for media even with v2 API)
    media_ids = []
    for media in images[:4]:  # X allows max 4 images per tweet
        image_data, content_type = _get_image_bytes_and_type(media.image)
        upload_resp = http_requests.post(
            f'{TWITTER_UPLOAD_BASE}/media/upload.json',
            headers=auth_headers,
            files={'media': ('image', image_data, content_type)},
            timeout=60,
        )
        upload_resp.raise_for_status()
        media_ids.append(upload_resp.json()['media_id_string'])

    # Create tweet
    tweet_payload = {'text': text}
    if media_ids:
        tweet_payload['media'] = {'media_ids': media_ids}

    tweet_resp = http_requests.post(
        f'{TWITTER_API_BASE}/tweets',
        headers={**auth_headers, 'Content-Type': 'application/json'},
        json=tweet_payload,
        timeout=30,
    )
    tweet_resp.raise_for_status()


# ─── Facebook ─────────────────────────────────────────────────────────────────


def publish_to_facebook(platform_variant, connection, base_url=''):
    """Publish to a Facebook Page using the Graph API."""
    access_token = connection.access_token
    page_id = connection.external_account_id
    text = platform_variant.get_effective_text()
    images = list(platform_variant.get_effective_media())

    if not images:
        # Text-only post
        resp = http_requests.post(
            f'{GRAPH_API_BASE}/{page_id}/feed',
            data={'message': text, 'access_token': access_token},
            timeout=30,
        )
        resp.raise_for_status()
    elif len(images) == 1:
        # Single-image post (creates the post directly)
        image_data, content_type = _get_image_bytes_and_type(images[0].image)
        resp = http_requests.post(
            f'{GRAPH_API_BASE}/{page_id}/photos',
            data={'message': text, 'access_token': access_token},
            files={'source': ('image', image_data, content_type)},
            timeout=60,
        )
        resp.raise_for_status()
    else:
        # Multi-image: upload each photo as unpublished, then create feed post
        photo_ids = []
        for media in images[:10]:  # Facebook max 10
            image_data, content_type = _get_image_bytes_and_type(media.image)
            photo_resp = http_requests.post(
                f'{GRAPH_API_BASE}/{page_id}/photos',
                data={'published': 'false', 'access_token': access_token},
                files={'source': ('image', image_data, content_type)},
                timeout=60,
            )
            photo_resp.raise_for_status()
            photo_ids.append(photo_resp.json()['id'])

        import json as _json
        feed_resp = http_requests.post(
            f'{GRAPH_API_BASE}/{page_id}/feed',
            data={
                'message': text,
                'access_token': access_token,
                'attached_media': _json.dumps([{'media_fbid': pid} for pid in photo_ids]),
            },
            timeout=30,
        )
        feed_resp.raise_for_status()


# ─── Instagram ────────────────────────────────────────────────────────────────


def publish_to_instagram(platform_variant, connection, base_url=''):
    """
    Publish to Instagram using the Instagram Graph API.
    Images must be accessible via public URL.
    Single images → single media container.
    Multiple images → carousel container.
    """
    access_token = connection.access_token
    ig_user_id = connection.external_account_id
    text = platform_variant.get_effective_text()
    images = list(platform_variant.get_effective_media())

    if not images:
        raise ValueError('Instagram requires at least one image to publish.')

    if len(images) == 1:
        image_url = _get_absolute_image_url(images[0].image, base_url)
        container_resp = http_requests.post(
            f'{IG_GRAPH_BASE}/{ig_user_id}/media',
            data={
                'image_url': image_url,
                'caption': text,
                'access_token': access_token,
            },
            timeout=30,
        )
        container_resp.raise_for_status()
        container_id = container_resp.json()['id']
    else:
        # Carousel: create one item container per image first
        item_ids = []
        for media in images[:10]:  # Instagram carousel max 10
            image_url = _get_absolute_image_url(media.image, base_url)
            item_resp = http_requests.post(
                f'{IG_GRAPH_BASE}/{ig_user_id}/media',
                data={
                    'image_url': image_url,
                    'is_carousel_item': 'true',
                    'access_token': access_token,
                },
                timeout=30,
            )
            item_resp.raise_for_status()
            item_ids.append(item_resp.json()['id'])

        carousel_resp = http_requests.post(
            f'{IG_GRAPH_BASE}/{ig_user_id}/media',
            data={
                'media_type': 'CAROUSEL',
                'children': ','.join(item_ids),
                'caption': text,
                'access_token': access_token,
            },
            timeout=30,
        )
        carousel_resp.raise_for_status()
        container_id = carousel_resp.json()['id']

    # Publish the container
    publish_resp = http_requests.post(
        f'{IG_GRAPH_BASE}/{ig_user_id}/media_publish',
        data={
            'creation_id': container_id,
            'access_token': access_token,
        },
        timeout=30,
    )
    publish_resp.raise_for_status()


# ─── Platform registry ───────────────────────────────────────────────────────

_PLATFORM_PUBLISHERS = {
    'linkedin': publish_to_linkedin,
    'facebook': publish_to_facebook,
    'x': publish_to_twitter,
    'instagram': publish_to_instagram,
}

# Maps the social_media platform key to the integrations provider key
_PLATFORM_TO_PROVIDER = {
    'linkedin': 'linkedin',
    'facebook': 'facebook',
    'x': 'twitter',
    'instagram': 'instagram',
}


# ─── Central publish ─────────────────────────────────────────────────────────


def publish_post(post, project, base_url=''):
    """
    Publish a SocialMediaPost to all enabled platforms that have an active
    IntegrationConnection on the project.

    Returns a dict mapping platform key → result dict::

        {
            'linkedin': {'success': True,  'error': None},
            'instagram': {'success': False, 'error': 'Instagram requires ...'},
        }

    Also updates:
    - SocialMediaPostPlatform.published_at / publish_error per platform
    - SocialMediaPost.status = 'published' and published_at if any platform succeeded
    """
    # Index active social-media connections by provider key
    connections = {
        conn.provider: conn
        for conn in IntegrationConnection.objects.filter(
            project=project,
            provider_category=IntegrationConnection.ProviderCategory.SOCIAL_MEDIA,
            status=IntegrationConnection.ConnectionStatus.ACTIVE,
        )
    }

    results = {}
    now = timezone.now()
    any_success = False

    for platform_variant in post.platforms.filter(is_enabled=True).select_related('post'):
        platform = platform_variant.platform
        provider_key = _PLATFORM_TO_PROVIDER.get(platform)
        connection = connections.get(provider_key)

        if not connection:
            results[platform] = {'success': False, 'error': 'No active connection for this platform.'}
            continue

        publisher_fn = _PLATFORM_PUBLISHERS.get(platform)
        if not publisher_fn:
            results[platform] = {'success': False, 'error': 'Unsupported platform.'}
            continue

        try:
            publisher_fn(platform_variant, connection, base_url)
            platform_variant.published_at = now
            platform_variant.publish_error = ''
            platform_variant.save(update_fields=['published_at', 'publish_error'])
            results[platform] = {'success': True, 'error': None}
            any_success = True
        except Exception as exc:
            error_msg = str(exc)
            logger.exception('Failed to publish post %d to %s', post.pk, platform)
            platform_variant.publish_error = error_msg[:500]
            platform_variant.save(update_fields=['publish_error'])
            results[platform] = {'success': False, 'error': error_msg}

    if any_success:
        post.status = 'published'
        post.published_at = now
        post.save(update_fields=['status', 'published_at'])

    return results
