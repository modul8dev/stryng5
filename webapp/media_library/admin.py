from django.contrib import admin

from .models import Image, ImageGroup


class ImageInline(admin.TabularInline):
    model = Image
    extra = 1


@admin.register(ImageGroup)
class ImageGroupAdmin(admin.ModelAdmin):
    list_display = ['title', 'created_at']
    search_fields = ['title']
    inlines = [ImageInline]


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'image_group', 'created_at']
    list_filter = ['image_group']
