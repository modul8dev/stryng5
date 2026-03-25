from django.urls import path
from .views import home, settings

urlpatterns = [
    path("", home, name="home"),
    path("settings", settings, name="settings"),
]
