from django.urls import path
from . import views

urlpatterns = [
    path('', views.campaign_home, name='announced-campaign-home'),
    path('start/<int:run_id>/', views.user_start, name='announced-campaign-start'),
    path('launch/<int:run_id>/', views.launch_campaign, name='announced-campaign-launch'),
    path('scenario/<int:run_id>/<int:position>/', views.scenario_runner, name='announced-scenario-runner'),
    path('complete/<int:run_id>/', views.campaign_complete, name='announced-campaign-complete'),
]