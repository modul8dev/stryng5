from django.conf import settings
from django.db import models


PLATFORM_CHOICES = [
    ('linkedin', 'LinkedIn'),
    ('x', 'X (Twitter)'),
    ('facebook', 'Facebook'),
    ('instagram', 'Instagram'),
]

PLATFORM_CHAR_LIMITS = {
    'linkedin': 3000,
    'x': 280,
    'facebook': 63206,
    'instagram': 2200,
}

PLATFORM_IMAGE_LIMITS = {
    'linkedin': 9,
    'x': 4,
    'facebook': 10,
    'instagram': 10,
}

STATUS_CHOICES = [
    ('draft', 'Draft'),
    ('scheduled', 'Scheduled'),
    ('published', 'Published'),
    ('failed', 'Failed'),
]


POST_TYPE_CHOICES = [
    ('product', 'Product'),
    ('lifestyle', 'Lifestyle'),
    ('ad', 'Ad'),
]


class SocialMediaPost(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='social_media_posts',
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='social_media_posts',
    )
    title = models.CharField(max_length=200)
    shared_text = models.TextField(blank=True)
    topic = models.CharField(max_length=300, blank=True)
    post_type = models.CharField(max_length=20, choices=POST_TYPE_CHOICES, blank=True)
    ai_instruction = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    scheduled_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class SocialMediaPostPlatform(models.Model):
    post = models.ForeignKey(
        SocialMediaPost,
        on_delete=models.CASCADE,
        related_name='platforms',
    )
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    is_enabled = models.BooleanField(default=True)
    use_shared_text = models.BooleanField(default=True)
    override_text = models.TextField(blank=True)
    use_shared_media = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True)
    publish_error = models.TextField(blank=True, default='')

    class Meta:
        unique_together = [('post', 'platform')]

    def get_effective_text(self):
        if self.use_shared_text:
            return self.post.shared_text
        return self.override_text

    def get_effective_media(self):
        if self.use_shared_media:
            return self.post.shared_media.order_by('sort_order')
        return self.override_media.order_by('sort_order')

    def __str__(self):
        return f'{self.post.title} — {self.get_platform_display()}'


class SocialMediaPostMedia(models.Model):
    post = models.ForeignKey(
        SocialMediaPost,
        on_delete=models.CASCADE,
        related_name='shared_media',
    )
    image = models.ForeignKey(
        'media_library.Image',
        on_delete=models.CASCADE,
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order']

    def __str__(self):
        return f'Shared media for {self.post.title}: {self.image}'


class SocialMediaPostSeedImage(models.Model):
    post = models.ForeignKey(
        SocialMediaPost,
        on_delete=models.CASCADE,
        related_name='seed_images',
    )
    image = models.ForeignKey(
        'media_library.Image',
        on_delete=models.CASCADE,
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order']

    def __str__(self):
        return f'Seed image for {self.post.title}: {self.image}'


class SocialMediaPlatformMedia(models.Model):
    platform_variant = models.ForeignKey(
        SocialMediaPostPlatform,
        on_delete=models.CASCADE,
        related_name='override_media',
    )
    image = models.ForeignKey(
        'media_library.Image',
        on_delete=models.CASCADE,
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order']

    def __str__(self):
        return f'Override media for {self.platform_variant}: {self.image}'
