from django.conf import settings
from django.db import models
from core import fields


class Brand(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='brands',
    )
    project = models.OneToOneField(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='brand',
    )
    website_url = models.URLField(blank=True)
    name = fields.TruncatingCharField(max_length=255, blank=True)
    summary = models.TextField(blank=True)
    language = fields.TruncatingCharField(max_length=10, blank=True)
    style_guide = models.TextField(blank=True)
    tone_of_voice = models.TextField(blank=True)
    target_audience = models.TextField(blank=True)
    fonts = models.TextField(blank=True)
    primary_color = fields.TruncatingCharField(max_length=7, blank=True)
    secondary_color = fields.TruncatingCharField(max_length=7, blank=True)
    logo = models.ForeignKey(
        'media_library.MediaGroup',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='logo_brands',
    )
    class ProcessingStatus(models.TextChoices):
        IDLE = 'idle', 'Idle'
        SCRAPING = 'scraping', 'Scraping'
        ERROR = 'error', 'Error'

    processing_status = fields.TruncatingCharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.IDLE,
    )
    scrape_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name or f'Brand for {self.user.email}'

    @property
    def has_data(self):
        return bool(self.name or self.summary)

