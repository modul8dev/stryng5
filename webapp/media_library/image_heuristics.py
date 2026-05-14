import re
from collections import Counter
from urllib.parse import unquote, urljoin, urlparse


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
    'product_media',
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
    'brand_media',
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
    'product_media',
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
_STYLE_SEGMENT_RE = re.compile(r'/media_style/[^/]+/', re.IGNORECASE)
_GENERIC_STYLE_SEGMENT_RE = re.compile(r'/styles/[^/]+/', re.IGNORECASE)
_QUALITY_DIMENSION_RE = re.compile(r'([_-])(\d{2,4})x(\d{2,4})(?=\.[a-z0-9]+$)', re.IGNORECASE)
_PRODUCT_STYLE_SIZE_RE = re.compile(r'/product_(\d{2,4})(?:/|$)', re.IGNORECASE)


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


def _normalize_media_path(path):
    normalized = unquote(path or '').lower()
    normalized = _STYLE_SEGMENT_RE.sub('/', normalized)
    normalized = _GENERIC_STYLE_SEGMENT_RE.sub('/', normalized)
    normalized = _DOUBLE_FORMAT_RE.sub(r'.\1', normalized)
    normalized = _DIMENSION_SUFFIX_RE.sub('', normalized)
    normalized = _AT_SCALE_SUFFIX_RE.sub('', normalized)
    normalized = re.sub(r'//+', '/', normalized)
    return normalized


def _normalize_media_identity(media_url):
    parsed = urlparse(media_url)
    normalized_path = _normalize_media_path(parsed.path)
    return f'{_domain_key(parsed.hostname)}{normalized_path}'


def _is_obvious_non_product_asset(media_url):
    parsed = urlparse(media_url)
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


def _media_variant_quality(media_url):
    path = unquote(urlparse(media_url).path or '').lower()
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


def _media_candidate_score(media_url, page_url='', page_title='', page_description='', asset_page_count=1, total_pages=1):
    page_score = _page_product_score(page_url=page_url, title=page_title, description=page_description)
    parsed = urlparse(media_url)
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
    if _is_obvious_non_product_asset(media_url):
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


def _select_distinct_product_media_urls(
    media_urls,
    page_url='',
    page_title='',
    page_description='',
    asset_page_counts=None,
    total_pages=1,
):
    asset_page_counts = asset_page_counts or Counter()
    page_score = _page_product_score(page_url=page_url, title=page_title, description=page_description)
    best_by_identity = {}

    for index, raw_url in enumerate(media_urls):
        url = (raw_url or '').strip()
        if not url or url.startswith('data:'):
            continue

        absolute_url = urljoin(page_url, url)
        identity = _normalize_media_identity(absolute_url)
        if not identity:
            continue

        asset_page_count = asset_page_counts.get(identity, 1)
        candidate = {
            'url': absolute_url,
            'index': index,
            'asset_page_count': asset_page_count,
            'score': _media_candidate_score(
                absolute_url,
                page_url=page_url,
                page_title=page_title,
                page_description=page_description,
                asset_page_count=asset_page_count,
                total_pages=total_pages,
            ),
            'quality': _media_variant_quality(absolute_url),
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
    media_urls = []
    for media in getattr(doc, 'media', None) or []:
        if isinstance(media, dict):
            value = media.get('src') or media.get('url') or ''
        else:
            value = getattr(media, 'src', None) or getattr(media, 'url', None) or str(media)
        value = (value or '').strip()
        if value:
            media_urls.append(value)

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
        'media_urls': media_urls,
    }


def deduplicate_media_for_project(project, threshold_ratio=0.35):
    """
    Remove Media objects that appear across too many MediaGroups for a project —
    these are site-wide repeated images (icons, logos, social badges, etc.).

    Strategy:
    - Normalize each external_url with _normalize_media_identity to collapse CDN
      variants and size suffixes to a canonical identity.
    - Count how many distinct MediaGroups each identity appears in.
    - Delete any Media whose identity appears in >= threshold groups
      (threshold = max(2, floor(n_groups * threshold_ratio))).
    - Delete MediaGroups that are left completely empty after dedup.
    """
    from math import floor
    from .models import Media, MediaGroup

    groups = list(
        MediaGroup.objects.filter(project=project, type=MediaGroup.GroupType.PRODUCT)
        .prefetch_related('media_items')
    )
    n_groups = len(groups)
    if n_groups < 2:
        return

    threshold = max(2, floor(n_groups * threshold_ratio))

    # Build identity -> set of group PKs
    identity_groups: dict[str, set] = {}
    # Build identity -> list of Media PKs
    identity_media_pks: dict[str, list] = {}

    for group in groups:
        for media in group.media_items.all():
            url = (media.external_url or '').strip()
            if not url:
                continue
            identity = _normalize_media_identity(url)
            if not identity:
                continue
            identity_groups.setdefault(identity, set()).add(group.pk)
            identity_media_pks.setdefault(identity, []).append(media.pk)

    # Also filter obvious non-product assets regardless of threshold
    repeated_pks = []
    for identity, group_pks in identity_groups.items():
        # Pick any url for this identity to run the obvious-non-product check
        sample_pks = identity_media_pks[identity]
        sample_media = Media.objects.filter(pk=sample_pks[0]).first()
        sample_url = sample_media.external_url if sample_media else ''
        if len(group_pks) >= threshold or _is_obvious_non_product_asset(sample_url):
            repeated_pks.extend(identity_media_pks[identity])

    if repeated_pks:
        Media.objects.filter(pk__in=repeated_pks).delete()

    # Remove MediaGroups that are now empty
    MediaGroup.objects.filter(
        project=project,
        type=MediaGroup.GroupType.PRODUCT,
        media_items__isnull=True,
    ).delete()
