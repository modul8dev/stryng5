from django.contrib import admin

from .models import Brand


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['user', 'name', 'website_url', 'created_at']
    search_fields = ['user__email', 'name', 'website_url']
    readonly_fields = ['created_at', 'updated_at']

