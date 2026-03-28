import io
import os

from django.core.files.base import ContentFile

from media_library.models import Image, ImageGroup
from prompts.social_media_edit import SOCIAL_MEDIA_EDIT_ACTIONS, SOCIAL_MEDIA_EDIT_SYSTEM
from prompts.social_media_generate import SOCIAL_MEDIA_GENERATE_PROMPT
from prompts.social_media_topic import SOCIAL_MEDIA_TOPIC_PROMPT


def _get_openai_client():
    from openai import OpenAI
    return OpenAI(api_key=os.environ.get('OPENAI_API_KEY', ''))


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
        'brand_language': brand.language or 'English',
        'brand_style_guide': brand.style_guide or '',
    }


def suggest_topic(brand, seed_images):
    """Suggest topics based on brand context and seed images. Returns a list."""
    import re
    client = _get_openai_client()
    ctx = _get_brand_context(brand)
    prompt = SOCIAL_MEDIA_TOPIC_PROMPT.format(
        image_descriptions=_build_image_descriptions(seed_images),
        **ctx,
    )
    response = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{'role': 'user', 'content': prompt}],
        temperature=0.7,
        max_tokens=300,
    )
    raw = response.choices[0].message.content.strip()
    topics = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        cleaned = re.sub(r'^\d+\.\s*', '', line)
        if cleaned:
            topics.append(cleaned)
    return topics if topics else [raw]


def generate_post_text(brand, topic, post_type, seed_images, platforms):
    """Generate post text using OpenAI."""
    client = _get_openai_client()
    ctx = _get_brand_context(brand)
    prompt = SOCIAL_MEDIA_GENERATE_PROMPT.format(
        topic=topic or 'general brand post',
        post_type=post_type or 'lifestyle',
        platforms=', '.join(platforms) if platforms else 'general',
        image_descriptions=_build_image_descriptions(seed_images),
        **ctx,
    )
    response = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{'role': 'user', 'content': prompt}],
        temperature=0.7,
        max_tokens=1000,
    )
    return response.choices[0].message.content.strip()


def generate_post_image(brand, topic, post_type, seed_images, user):
    """Generate an image using Gemini and save it to the media library."""
    from io import BytesIO
    from PIL import Image as PILImage
    from google.genai import types

    client = _get_gemini_client()

    # Build pre-prompt: include seed image names/descriptions and instruct AI
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

    # Open seed images as PIL images and pass alongside the prompt
    import urllib.request
    pil_images = []
    try:
        for img in (seed_images or []):
            try:
                if img.image and img.image.name:
                    pil_images.append(PILImage.open(img.image.path))
                elif img.external_url:
                    with urllib.request.urlopen(img.external_url) as resp:  # noqa: S310
                        pil_images.append(PILImage.open(BytesIO(resp.read())))
            except Exception:
                pass

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

    # Use the same image group as the seed images; fall back to a dedicated group
    if seed_images:
        group = seed_images[0].image_group
    else:
        group, _ = ImageGroup.objects.get_or_create(
            user=user,
            title='AI Generated Images',
            type=ImageGroup.GroupType.MANUAL,
        )

    # Extract image from response and save to media library
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            image_data = part.inline_data.data
            mime_type = part.inline_data.mime_type
            ext = 'png' if 'png' in mime_type else 'jpg'
            image_obj = Image(image_group=group)
            filename = f'ai_generated.{ext}'
            image_obj.image.save(filename, ContentFile(image_data), save=True)
            return image_obj

    return None


def edit_text(action, text, brand, platform=None, instruction=None):
    """Apply an AI edit action to text."""
    client = _get_openai_client()
    ctx = _get_brand_context(brand)

    action_template = SOCIAL_MEDIA_EDIT_ACTIONS.get(action)
    if not action_template:
        raise ValueError(f'Unknown action: {action}')

    user_prompt = action_template.format(
        text=text,
        platform=platform or '',
        instruction=instruction or '',
    )
    system_prompt = SOCIAL_MEDIA_EDIT_SYSTEM.format(**ctx)

    response = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        temperature=0.5,
        max_tokens=1000,
    )
    return response.choices[0].message.content.strip()
