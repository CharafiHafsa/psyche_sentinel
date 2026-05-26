from django.urls import path
from . import views

urlpatterns = [
    # Mettez à jour la ligne ci-dessous avec le bon nom de fonction :
    path('dashboard/', views.campaign_dashboard_view, name='ml_dashboard'),
]