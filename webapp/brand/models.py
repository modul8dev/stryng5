from django.conf import settings
from django.db import models


class Brand(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='brand',
    )
    website_url = models.URLField(blank=True)
    name = models.CharField(max_length=255, blank=True)
    summary = models.TextField(blank=True)
    language = models.CharField(max_length=100, blank=True)
    style_guide = models.TextField(blank=True)
    logo = models.ForeignKey(
        'media_library.ImageGroup',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='logo_brands',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name or f'Brand for {self.user.email}'

    @property
    def has_data(self):
        return bool(self.name or self.summary)


    def __str__(self):
        return self.name or f'Brand for {self.user.email}'

    @property
    def has_data(self):
        return bool(self.name or self.summary)

