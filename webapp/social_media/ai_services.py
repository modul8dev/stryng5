import io
import os
from enum import Enum

from django.core.files.base import ContentFile

from media_library.models import Image, ImageGroup
from prompts.social_media_edit import EDIT_ACTIONS, SOCIAL_MEDIA_EDIT_SYSTEM, SYSTEM_PROMPTS
from prompts.social_media_generate import SOCIAL_MEDIA_GENERATE_PROMPT
from prompts.social_media_topic import SOCIAL_MEDIA_TOPIC_PROMPT


class OpenAIModel(Enum):
    QUICK = 'gpt-4o-mini'
    NORMAL = 'gpt-4o'
    FULL = 'o1'


def _get_openai_client():
    from openai import OpenAI
    return OpenAI(api_key=os.environ.get('OPENAI_API_KEY', ''))


def _openai_chat(messages, model=OpenAIModel.QUICK, temperature=0.7, max_tokens=1000):
    """Send a chat request to OpenAI and return the response text."""
    client = _get_openai_client()
    response = client.chat.completions.create(
        model=model.value,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
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
        'brand_language': brand.language or 'English',
        'brand_style_guide': brand.style_guide or '',
    }


def suggest_topic(brand, seed_images):
    """Suggest topics based on brand context and seed images. Returns a list."""
    import re
    ctx = _get_brand_context(brand)
    prompt = SOCIAL_MEDIA_TOPIC_PROMPT.format(
        image_descriptions=_build_image_descriptions(seed_images),
        **ctx,
    )
    raw = _openai_chat(
        messages=[{'role': 'user', 'content': prompt}],
        max_tokens=300,
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


def generate_post_text(brand, topic, post_type, seed_images, platforms):
    """Generate post text using OpenAI."""
    ctx = _get_brand_context(brand)
    prompt = SOCIAL_MEDIA_GENERATE_PROMPT.format(
        topic=topic or 'general brand post',
        post_type=post_type or 'lifestyle',
        platforms=', '.join(platforms) if platforms else 'general',
        image_descriptions=_build_image_descriptions(seed_images),
        **ctx,
    )
    return _openai_chat(messages=[{'role': 'user', 'content': prompt}])


def _generate_gemini_image(prompt, input_images=None):
    """Call Gemini image generation and return (image_data, mime_type) or None."""
    from io import BytesIO
    import urllib.request
    from PIL import Image as PILImage
    from google.genai import types

    client = _get_gemini_client()
    pil_images = []
    try:
        for img in (input_images or []):
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

    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            return part.inline_data.data, part.inline_data.mime_type

    return None


def generate_post_image(brand, topic, post_type, seed_images, user):
    """Generate an image using Gemini and save it to the media library."""
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

    result = _generate_gemini_image(prompt, input_images=seed_images)
    if result is None:
        return None

    image_data, mime_type = result

    # Use the same image group as the seed images; fall back to a dedicated group
    if seed_images:
        group = seed_images[0].image_group
    else:
        group, _ = ImageGroup.objects.get_or_create(
            user=user,
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

    return _openai_chat(
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        temperature=0.5,
    )


def generate_editor_image(prompt, input_images, brand, user, output_group):
    """Generate an image via the Image Editor using Gemini and save to output_group."""
    # Inject brand context into the prompt
    if brand:
        brand_context = _get_brand_context(brand)

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
