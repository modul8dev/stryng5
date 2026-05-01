import os
from enum import Enum

from django.core.files.base import ContentFile

from media_library.models import Image, ImageGroup
from services.prompts.social_media_edit import EDIT_ACTIONS, SOCIAL_MEDIA_EDIT_SYSTEM, SYSTEM_PROMPTS
from services.prompts.social_media_generate import SOCIAL_MEDIA_GENERATE_PROMPT
from services.prompts.social_media_image import IMAGE_PRE_PROMPTS, IMAGE_TYPOGRAPHY_SUFFIX, IMAGE_VISUAL_FIDELITY_SUFFIX
from services.prompts.social_media_topic import SOCIAL_MEDIA_TOPIC_PROMPT


class OpenAIModel(Enum):
    QUICK = 'gpt-5-nano'
    NORMAL = 'gpt-5-mini'
    FULL = 'gpt-5'


def _get_openai_client():
    from openai import OpenAI
    return OpenAI(api_key=os.environ.get('OPENAI_API_KEY', ''))


def _openai_chat(messages, model=OpenAIModel.QUICK, **kwargs):
    """Send a chat request to OpenAI and return the response text."""
    client = _get_openai_client()
    kwargs.setdefault("reasoning_effort", "low")
    kwargs.update(
        model=model.value,
        messages=messages,
    )
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content.strip()


def _get_gemini_client():
    from google import genai
    return genai.Client(api_key=os.environ.get('GOOGLE_API_KEY', ''))


def _build_image_descriptions(seed_images):
    if not seed_images:
        return ''
    lines = ['Seed images provided as context:']
    for i, img in enumerate(seed_images, 1):
        description = str(img.image_group.description)
        title = img.image_group.title
        img_context = f'Title:{title} - Description:{description}' if description else title
        lines.append(f'  {i}. {img_context}')
    return '\n'.join(lines)


def _get_brand_context(brand):
    return {
        'brand_name': brand.name or 'Unknown',
        'brand_summary': brand.summary or '',
        'brand_style_guide': brand.style_guide or '',
    }


def _get_language_instruction(brand):
    """Return a concrete language instruction string based on the project language."""
    project = brand.project
    language_code = getattr(project, 'language', '') or 'en'
    from django.conf.global_settings import LANGUAGES
    language_name = dict(LANGUAGES).get(language_code, 'English')
    from services.prompts.language import get_language_instruction
    return get_language_instruction(language_name)


def extract_brand_data(markdown_content, language_instruction=None):
    """Extract structured brand data from markdown content using OpenAI. Returns a dict."""
    import json
    from services.prompts.brand_extract import BRAND_EXTRACT_PROMPT

    system_content = BRAND_EXTRACT_PROMPT
    if language_instruction:
        system_content = system_content.rstrip() + f'\n{language_instruction}'

    raw = _openai_chat(
        messages=[
            {'role': 'system', 'content': system_content},
            {'role': 'user', 'content': markdown_content[:20000]},
        ],
        response_format={'type': 'json_object'},
    )
    return json.loads(raw)


def select_brand_urls(all_urls, base_url):
    """
    Ask the LLM to pick the 5-7 URLs from all_urls most likely to contain brand data.
    Returns a list of URL strings (subset of all_urls).
    """
    import json
    from services.prompts.brand_extract import BRAND_URL_SELECT_PROMPT

    url_list = '\n'.join(all_urls[:200])  # cap to avoid token overflow
    user_msg = f'Website: {base_url}\n\nAvailable URLs:\n{url_list}'
    raw = _openai_chat(
        messages=[
            {'role': 'system', 'content': BRAND_URL_SELECT_PROMPT},
            {'role': 'user', 'content': user_msg},
        ],
        response_format={'type': 'json_object'},
        model=OpenAIModel.QUICK,
    )
    # The prompt asks for a JSON array, but json_object mode requires an object.
    # Handle both {"urls": [...]} and a bare list wrapped in an object.
    parsed = json.loads(raw)
    if isinstance(parsed, list):
        selected = parsed
    elif isinstance(parsed, dict):
        # Try common wrapper keys
        for key in ('urls', 'selected', 'pages', 'links'):
            if key in parsed and isinstance(parsed[key], list):
                selected = parsed[key]
                break
        else:
            # Fall back to first list value found
            selected = next((v for v in parsed.values() if isinstance(v, list)), [])
    else:
        selected = []

    # Return only valid strings that were in the original list
    all_urls_set = set(all_urls)
    return [u for u in selected if isinstance(u, str) and u in all_urls_set]


def suggest_topic(brand, seed_images):
    """Suggest topics based on brand context and seed images. Returns a list."""
    import re
    ctx = _get_brand_context(brand)
    lang = _get_language_instruction(brand)
    prompt = SOCIAL_MEDIA_TOPIC_PROMPT.format(
        image_descriptions=_build_image_descriptions(seed_images),
        **ctx,
    )
    raw = _openai_chat(
        messages=[
            {'role': 'system', 'content': lang},
            {'role': 'user', 'content': prompt},
        ],
    )
    topics = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        cleaned = re.sub(r'^\d+\.\s*', '', line)
        if cleaned:
            topics.append(cleaned)
    return topics if topics else [raw]

def _generate_gemini_image(prompt, input_images=None):
    """Call Gemini image generation and return (image_data, mime_type) or None."""
    from io import BytesIO
    import requests
    from PIL import Image as PILImage
    from google.genai import types

    _browser_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    client = _get_gemini_client()
    def _open_as_pil(path_or_bytes, is_bytes=False):
        """Open an image as PIL, converting SVG to PNG via cairosvg if needed."""
        if is_bytes:
            return PILImage.open(BytesIO(path_or_bytes))
        if path_or_bytes.lower().endswith('.svg'):
            import cairosvg
            png_bytes = cairosvg.svg2png(url=path_or_bytes)
            return PILImage.open(BytesIO(png_bytes))
        return PILImage.open(path_or_bytes)

    pil_images = []
    try:
        for img in (input_images or []):
            if img.image and img.image.name:
                pil_images.append(_open_as_pil(img.image.path))
            elif img.external_url:
                try:
                    resp = requests.get(img.external_url, headers=_browser_headers, timeout=15)
                    resp.raise_for_status()
                    content_type = resp.headers.get('Content-Type', '')
                    if 'svg' in content_type or img.external_url.lower().endswith('.svg'):
                        import cairosvg
                        png_bytes = cairosvg.svg2png(bytestring=resp.content)
                        pil_images.append(PILImage.open(BytesIO(png_bytes)))
                    else:
                        pil_images.append(PILImage.open(BytesIO(resp.content)))
                except requests.RequestException as exc:
                    raise RuntimeError(f'Failed to fetch image from {img.external_url}: {exc}') from exc

        contents = [prompt] + pil_images

        response = client.models.generate_content(
            model='gemini-3.1-flash-image-preview',
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=['IMAGE'],
                image_config=types.ImageConfig(
                    aspect_ratio="9:16"
                )
            ),
        )
    finally:
        for pil_img in pil_images:
            pil_img.close()

    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            return part.inline_data.data, part.inline_data.mime_type

    return None

def generate_post_text(brand, topic, post_type, seed_images, platforms):
    """Generate post text using OpenAI."""
    ctx = _get_brand_context(brand)
    lang = _get_language_instruction(brand)
    prompt = SOCIAL_MEDIA_GENERATE_PROMPT.format(
        topic=topic or 'general brand post',
        post_type=post_type or 'lifestyle',
        platforms=', '.join(platforms) if platforms else 'general',
        image_descriptions=_build_image_descriptions(seed_images),
        **ctx,
    )
    return _openai_chat(messages=[
        {'role': 'system', 'content': lang},
        {'role': 'user', 'content': prompt},
    ])

def _generate_image_prompt(brand, topic, post_type, seed_images):
    """Use OpenAI to generate a detailed image prompt based on brand, topic, post type, and seed images."""
    pre_prompt_template = IMAGE_PRE_PROMPTS.get((post_type or '').lower())
    if not pre_prompt_template:
        return None

    ctx = _get_brand_context(brand)
    brand_info = (
        f"Name: {ctx['brand_name']}\n"
        f"Summary: {ctx['brand_summary']}\n"
        f"Style: {ctx['brand_style_guide']}"
    )
    product_info = _build_image_descriptions(seed_images) or 'No product reference provided.'

    pre_prompt = pre_prompt_template.format(
        brand_info=brand_info,
        product_info=product_info,
        topic=topic or 'general brand post',
    )

    image_prompt = _openai_chat(
        messages=[{'role': 'user', 'content': pre_prompt}],
        model=OpenAIModel.NORMAL,
    )

    if (post_type or '').lower() in ('product', 'lifestyle'):
        image_prompt += IMAGE_TYPOGRAPHY_SUFFIX
    image_prompt += IMAGE_VISUAL_FIDELITY_SUFFIX

    return image_prompt


def generate_post_image(brand, topic, post_type, seed_images, user, project=None):
    """Generate an image using Gemini and save it to the media library."""
    # Step 1: generate a detailed image prompt via OpenAI
    prompt = _generate_image_prompt(brand, topic, post_type, seed_images)

    # Fallback to a simple prompt if no matching pre-prompt template exists
    if not prompt:
        seed_lines = []
        if seed_images:
            seed_lines.append('Reference images provided for context and style inspiration:')
            for i, img in enumerate(seed_images, 1):
                name = img.image.name.split('/')[-1] if img.image and img.image.name else str(img)
                description = str(img)
                seed_lines.append(f'  {i}. Name: {name} — {description}')
            seed_lines.append(
                'Use the reference images above to inform visual style, composition, and subject matter.'
            )
            seed_lines.append('')
        pre_prompt = '\n'.join(seed_lines) if seed_lines else ''
        prompt = (
            f"{pre_prompt}"
            f"Create a professional social media image for brand '{brand.name or 'brand'}'. "
            f"Topic: {topic or 'general'}. Post type: {post_type or 'lifestyle'}. "
            f"Style: {brand.style_guide or 'professional, clean, modern'}."
        )

    # Step 2: generate the actual image using the prompt
    result = _generate_gemini_image(prompt, input_images=seed_images)
    if result is None:
        return None

    image_data, mime_type = result

    if seed_images:
        group = seed_images[0].image_group
    else:
        group, _ = ImageGroup.objects.get_or_create(
            user=user,
            project=project,
            title='AI Generated Images',
            type=ImageGroup.GroupType.MANUAL,
        )

    ext = 'png' if 'png' in mime_type else 'jpg'
    image_obj = Image(image_group=group)
    image_obj.image.save(f'ai_generated.{ext}', ContentFile(image_data), save=True)
    return image_obj


def edit_text(action, text, brand, platform=None, instruction=None, system_prompt_key=None):
    """Apply an AI edit action to text."""
    ctx = _get_brand_context(brand)
    lang = _get_language_instruction(brand)

    action_template = EDIT_ACTIONS.get(action)
    if not action_template:
        raise ValueError(f'Unknown action: {action}')

    user_prompt = action_template.format(
        text=text,
        platform=platform or '',
        instruction=instruction or '',
    )
    system_prompt_template = SYSTEM_PROMPTS.get(system_prompt_key) if system_prompt_key else None
    system_prompt = (system_prompt_template or SOCIAL_MEDIA_EDIT_SYSTEM).format(**ctx)
    system_prompt = system_prompt.rstrip() + f'\n{lang}'

    return _openai_chat(
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
    )


def generate_editor_image(prompt, input_images, brand, user, output_group):
    """Generate an image via the Image Editor using Gemini and save to output_group."""
    brand_context = _get_brand_context(brand) if brand else None
    full_prompt = f"{brand_context} {prompt}".strip() if brand_context else prompt

    result = _generate_gemini_image(full_prompt, input_images=input_images)
    if result is None:
        return None

    image_data, mime_type = result
    ext = 'png' if 'png' in mime_type else 'jpg'
    image_obj = Image(
        image_group=output_group,
        image_type=Image.ImageType.GENERATED,
    )
    image_obj.image.save(f'ai_editor.{ext}', ContentFile(image_data), save=True)
    return image_obj
