from django.conf import settings
from django.db import models
from django.utils import timezone
from core import fields


class IntegrationConnection(models.Model):

    class ProviderCategory(models.TextChoices):
        SOCIAL_MEDIA = 'social_media', 'Social Media'
        MARKETING = 'marketing', 'Marketing'
        ECOMMERCE = 'ecommerce', 'E-Commerce'
        STORAGE = 'storage', 'Storage'
        OTHER = 'other', 'Other'

    class ConnectionStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        EXPIRED = 'expired', 'Expired'
        REVOKED = 'revoked', 'Revoked'
        ERROR = 'error', 'Error'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='integration_connections',
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='integration_connections',
    )
    provider = fields.TruncatingCharField(max_length=50)
    provider_category = fields.TruncatingCharField(
        max_length=50,
        choices=ProviderCategory.choices,
        default=ProviderCategory.OTHER,
    )
    external_account_id = fields.TruncatingCharField(max_length=255)
    external_account_name = fields.TruncatingCharField(max_length=255, blank=True, default='')
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True, default='')
    token_expires_at = models.DateTimeField(null=True, blank=True)
    scopes = models.TextField(blank=True, default='')
    status = fields.TruncatingCharField(
        max_length=20,
        choices=ConnectionStatus.choices,
        default=ConnectionStatus.ACTIVE,
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('project', 'provider', 'external_account_id')]

    def __str__(self):
        return f'{self.provider} – {self.external_account_name or self.external_account_id}'

    @property
    def is_expired(self):
        if self.token_expires_at is None:
            return False
        return timezone.now() >= self.token_expires_at

    def to_token(self):
        return {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'token_type': 'Bearer',
            'expires_at': int(self.token_expires_at.timestamp()) if self.token_expires_at else None,
        }
