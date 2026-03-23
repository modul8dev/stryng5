from django.urls import path

from . import views

app_name = 'media_library'

urlpatterns = [
    path('', views.image_group_list, name='image_group_list'),
    path('create/', views.image_group_create, name='image_group_create'),
    path('<int:pk>/edit/', views.image_group_edit, name='image_group_edit'),
    path('<int:pk>/delete/', views.image_group_delete, name='image_group_delete'),
]
