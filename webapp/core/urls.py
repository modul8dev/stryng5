"""
URL configuration for webapp project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.static import serve as static_serve

from media_library import views as ml_views

urlpatterns = [
    path('brand/', include('brand.urls')),
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('media-library/', include('media_library.urls')),
    path('catalog/', ml_views.catalog, name='catalog'),
    path('social-media/', include('social_media.urls')),
    path('scheduler/', include('scheduler.urls')),
    path('integrations/', include('integrations.urls')),
    path('projects/', include('projects.urls')),
    path('credits/', include('credits.urls')),
    path('events/', include('django_eventstream.urls')),
    path("", include("home.urls")),
]

if settings.DEBUG:
    urlpatterns += [
        re_path(
            r'^media/(?P<path>.*)$',
            login_not_required(static_serve),
            {'document_root': settings.MEDIA_ROOT},
        ),
    ]
