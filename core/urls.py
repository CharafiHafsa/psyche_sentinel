from django.urls import path
from . import views

urlpatterns = [
    # Leave this empty so it loads immediately at 127.0.0.1:8000/
    path('', views.landing_view, name='landing'), 
    
    path('login/', views.login_view, name='login'),
    path('deployment/', views.deployment_hub_view, name='deployment'),
    path('ui-kit/', views.ui_kit_view, name='ui-kit'),
]