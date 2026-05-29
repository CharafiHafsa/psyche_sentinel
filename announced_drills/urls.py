from django.urls import path
from . import views

urlpatterns = [
    path('', views.campaign_home, name='announced-campaign-home'),
    # path('start/<int:run_id>/', views.user_start, name='announced-campaign-start'),
    path('start/<int:run_id>/<str:signed_token>/', views.user_start, name='announced-campaign-start'),
    path('launch/<int:run_id>/', views.launch_campaign, name='announced-campaign-launch'),
    path('scenario/<int:run_id>/<int:position>/', views.scenario_runner, name='announced-scenario-runner'),
    path('complete/<int:run_id>/', views.campaign_complete, name='announced-campaign-complete'),
    path('attacks/', views.attack_scenarios_dashboard, name='announced-attacks-dashboard'),
path('campaign/<int:run_id>/results/', views.campaign_results_detail, name='announced-campaign-results'),
    path(
        'send/<int:run_id>/',
        views.send_campaign_emails,
        name='announced-campaign-send'
    ),
    path(
        'remind/<int:run_id>/',
        views.remind_campaign_pending_employees,
        name='announced-campaign-remind'
    ),
    path(
        'campaign/<int:run_id>/delete/',
        views.delete_campaign,
        name='announced-campaign-delete'
    ),
    path(
        'statistics/',
        views.global_statistics,
        name='announced-global-statistics'
    ),
]