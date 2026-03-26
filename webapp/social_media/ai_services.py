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
        label = str(img)
        lines.append(f'  {i}. {label}')
    return '\n'.join(lines)


def _get_brand_context(brand):
    return {
        'brand_name': brand.name or 'Unknown',
        'brand_summary': brand.summary or '',
        'brand_language': brand.language or 'English',
        'brand_style_guide': brand.style_guide or '',
    }


def suggest_topic(brand, seed_images):
    """Suggest a topic based on brand context and seed images."""
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
        max_tokens=100,
    )
    return response.choices[0].message.content.strip()


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
    client = _get_gemini_client()

    image_prompt = (
        f"Create a social media image for brand '{brand.name or 'brand'}'. "
        f"Topic: {topic or 'general'}. Post type: {post_type or 'lifestyle'}. "
        f"Style: professional, clean, modern."
    )

    response = client.models.generate_content(
        model='gemini-3.1-flash-image-preview',
        contents=image_prompt,
        config={
            'response_modalities': ['Image'],
        },
    )

    # Extract image from response
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            image_data = part.inline_data.data
            mime_type = part.inline_data.mime_type
            ext = 'png' if 'png' in mime_type else 'jpg'

            # Save to media library
            group, _ = ImageGroup.objects.get_or_create(
                user=user,
                title='AI Generated Images',
                type=ImageGroup.GroupType.MANUAL,
            )
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
