import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from core import fields


class Company(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = fields.TruncatingCharField(max_length=255, blank=True, default='')
    vat_id = fields.TruncatingCharField('VAT ID', max_length=64, blank=True, default='')
    address_line_1 = fields.TruncatingCharField(max_length=255, blank=True, default='')
    address_line_2 = fields.TruncatingCharField(max_length=255, blank=True, default='')
    city = fields.TruncatingCharField(max_length=100, blank=True, default='')
    state = fields.TruncatingCharField(max_length=100, blank=True, default='')
    zip_code = fields.TruncatingCharField(max_length=20, blank=True, default='')
    country = fields.TruncatingCharField(max_length=2, blank=True, default='', help_text='ISO 3166-1 alpha-2 country code')
    phone = fields.TruncatingCharField(max_length=32, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    website = models.URLField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'companies'

    def __str__(self):
        return self.name or str(self.uuid)


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    username = None
    email = models.EmailField('email address', unique=True)
    company_name = fields.TruncatingCharField(max_length=255, blank=True, default='')
    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
    )
    stripe_customer_id = fields.TruncatingCharField(max_length=255, blank=True, default='')
    stripe_subscription_id = fields.TruncatingCharField(max_length=255, blank=True, default='')

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()
