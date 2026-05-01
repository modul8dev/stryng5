from django.conf import settings
from django.conf.global_settings import LANGUAGES
from django.db import models


class Project(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='projects',
    )
    language = models.CharField(
        max_length=10,
        choices=LANGUAGES,
        default='en',
    )
    enable_linkedin = models.BooleanField(default=True)
    enable_x = models.BooleanField(default=True)
    enable_facebook = models.BooleanField(default=True)
    enable_instagram = models.BooleanField(default=True)
    product_import_in_progress = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def get_enabled_platforms(self):
        platforms = []
        if self.enable_linkedin:
            platforms.append('linkedin')
        if self.enable_x:
            platforms.append('x')
        if self.enable_facebook:
            platforms.append('facebook')
        if self.enable_instagram:
            platforms.append('instagram')
        return platforms
