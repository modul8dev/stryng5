from django.urls import path

from . import views

app_name = 'brand'

urlpatterns = [
    path('', views.brand_detail, name='brand_detail'),
    path('scrape-modal/', views.brand_scrape_modal, name='brand_scrape_modal'),
    path('onboarding/', views.brand_onboarding, name='brand_onboarding'),
]
