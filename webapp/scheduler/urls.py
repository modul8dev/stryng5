from django.urls import path

from . import views

app_name = 'scheduler'

urlpatterns = [
    path('', views.scheduler_view, name='scheduler'),
    path('api/events/', views.scheduler_events, name='scheduler_events'),
    path('api/event/<int:pk>/', views.scheduler_event_detail, name='scheduler_event_detail'),
    path('api/reschedule/<int:pk>/', views.scheduler_reschedule, name='scheduler_reschedule'),
]
