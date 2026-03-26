from django.contrib import admin

from .models import (
    SocialMediaSettings,
    SocialMediaPost,
    SocialMediaPostPlatform,
    SocialMediaPostMedia,
    SocialMediaPostSeedImage,
    SocialMediaPlatformMedia,
)


class SocialMediaPostPlatformInline(admin.TabularInline):
    model = SocialMediaPostPlatform
    extra = 0


class SocialMediaPostMediaInline(admin.TabularInline):
    model = SocialMediaPostMedia
    extra = 0


class SocialMediaPostSeedImageInline(admin.TabularInline):
    model = SocialMediaPostSeedImage
    extra = 0


@admin.register(SocialMediaPost)
class SocialMediaPostAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'status', 'created_at']
    list_filter = ['status']
    inlines = [SocialMediaPostPlatformInline, SocialMediaPostMediaInline, SocialMediaPostSeedImageInline]


@admin.register(SocialMediaSettings)
class SocialMediaSettingsAdmin(admin.ModelAdmin):
    list_display = ['user', 'enable_linkedin', 'enable_x', 'enable_facebook', 'enable_instagram']


@admin.register(SocialMediaPostPlatform)
class SocialMediaPostPlatformAdmin(admin.ModelAdmin):
    list_display = ['post', 'platform', 'is_enabled', 'use_shared_text', 'use_shared_media']
