SOCIAL_MEDIA_EDIT_ACTIONS = {
    'rewrite': 'Rewrite the following social media post in a different way while keeping the same meaning:\n\n{text}',
    'improve': 'Improve the following social media post to make it more polished and professional:\n\n{text}',
    'shorten': 'Shorten the following social media post while keeping the key message:\n\n{text}',
    'expand': 'Expand the following social media post with more detail and context:\n\n{text}',
    'make_engaging': 'Make the following social media post more engaging and attention-grabbing:\n\n{text}',
    'adapt_to_platform': 'Adapt the following social media post for {platform}. Follow platform best practices and character limits:\n\n{text}',
    'add_cta': 'Add a compelling call-to-action to the following social media post:\n\n{text}',
    'fix_grammar': 'Fix any grammar, spelling, or punctuation errors in the following social media post. Only fix errors, do not change the style:\n\n{text}',
    'freeform': '{instruction}\n\nApply the instruction above to the following social media post:\n\n{text}',
}

SOCIAL_MEDIA_EDIT_SYSTEM = """
You are a social media editor for the brand "{brand_name}".
Brand style guide: {brand_style_guide}
Brand language: {brand_language}

Return only the edited post text, no explanations or metadata.
"""
