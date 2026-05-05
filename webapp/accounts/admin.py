from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth import get_user_model

from .models import Company

User = get_user_model()


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'vat_id', 'city', 'country', 'created_at')
    search_fields = ('name', 'vat_id', 'email')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('id', 'name', 'vat_id', 'email', 'phone', 'website')}),
        ('Address', {'fields': ('address_line_1', 'address_line_2', 'city', 'state', 'zip_code', 'country')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    ordering = ('email',)
    list_display = ('email', 'first_name', 'last_name', 'company_name', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name', 'company_name')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'company_name', 'company')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
    )
