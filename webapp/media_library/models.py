from django.conf import settings
from django.db import models


class ImageGroup(models.Model):
    class GroupType(models.TextChoices):
        PRODUCT = 'product', 'Product'
        MANUAL = 'manual', 'Manual'
        GENERATED = 'generated', 'Generated'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='image_groups',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    type = models.CharField(
        max_length=20,
        choices=GroupType.choices,
        default=GroupType.MANUAL,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Image(models.Model):
    class ImageType(models.TextChoices):
        MANUAL = 'manual', 'Manual'
        GENERATED = 'generated', 'Generated'

    image_group = models.ForeignKey(
        ImageGroup,
        on_delete=models.CASCADE,
        related_name='images',
    )
    image = models.ImageField(upload_to='media_library/images/%Y/%m/', blank=True, null=True)
    external_url = models.URLField(blank=True)
    image_type = models.CharField(
        max_length=20,
        choices=ImageType.choices,
        default=ImageType.MANUAL,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def url(self):
        if self.image:
            return self.image.url
        return self.external_url

    def __str__(self):
        if self.image:
            return self.image.name
        if self.external_url:
            return self.external_url
        return f'Image {self.pk}'
