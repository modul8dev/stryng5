from django.conf import settings
from django.db import models


class ImageGroup(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='image_groups',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Image(models.Model):
    image_group = models.ForeignKey(
        ImageGroup,
        on_delete=models.CASCADE,
        related_name='images',
    )
    image = models.ImageField(upload_to='media_library/images/%Y/%m/')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.image.name if self.image else f'Image {self.pk}'
