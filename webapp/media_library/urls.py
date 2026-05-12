from django.urls import path

from . import views

app_name = 'media_library'

urlpatterns = [
    path('create/', views.media_group_create, name='media_group_create'),
    path('create/', views.media_group_create, name='media_group_create'),
    path('import-products/', views.products_import, name='products_import'),
    path('import-url/', views.url_import, name='url_import'),
    path('firecrawl-webhook/', views.firecrawl_webhook, name='firecrawl_webhook'),
    path('media-editor/', views.media_editor_modal, name='media_editor_modal'),
    path('media-editor/generate/', views.media_editor_generate, name='media_editor_generate'),
    path('<int:pk>/edit/', views.media_group_edit, name='media_group_edit'),
    path('<int:pk>/edit/', views.media_group_edit, name='media_group_edit'),
    path('<int:pk>/delete/', views.media_group_delete, name='media_group_delete'),
    path('<int:pk>/delete/', views.media_group_delete, name='media_group_delete'),
    path('media-picker/', views.media_picker, name='media_picker'),
    path('media-picker/', views.media_picker, name='media_picker'),
]
