from django.urls import path

from . import views

app_name = 'projects'

urlpatterns = [
    path('switch/', views.switch_project, name='switch_project'),
    path('create/', views.project_create, name='project_create'),
    path('create-quick/', views.project_create_quick, name='project_create_quick'),
    path('settings/', views.project_settings, name='project_settings'),
    path('provision/', views.project_provision, name='project_provision'),
    path('<int:pk>/edit/', views.project_edit, name='project_edit'),
    path('<int:pk>/delete/', views.project_delete, name='project_delete'),
]
