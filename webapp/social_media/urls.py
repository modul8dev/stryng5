from django.urls import path

from . import views

app_name = 'social_media'

urlpatterns = [
    path('', views.post_list, name='post_list'),
    path('create/', views.post_create, name='post_create'),
    path('<int:pk>/edit/', views.post_edit, name='post_edit'),
    path('<int:pk>/delete/', views.post_delete, name='post_delete'),
    path('<int:pk>/publish/', views.post_publish, name='post_publish'),
    path('<int:pk>/publish-info/', views.post_publish_info, name='post_publish_info'),
    path('<int:pk>/unschedule/', views.post_unschedule, name='post_unschedule'),
    path('ai/suggest-topic/', views.ai_suggest_topic, name='ai_suggest_topic'),
    path('ai/generate/', views.ai_generate, name='ai_generate'),
    path('ai/edit-text/', views.ai_edit_text, name='ai_edit_text'),
]
