# behavioral/urls.py
from django.urls import path
from . import views

app_name = 'behavioral'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('api/generate-agent/', views.generate_agent, name='generate_agent'),
    path('api/register/', views.agent_register, name='agent_register'),
    path('api/heartbeat/', views.agent_heartbeat, name='agent_heartbeat'),
    path('download/agent/', views.download_agent, name='download_agent'),
    path('agents/manage/', views.agent_management, name='agent_management'),
    path('audit/legal-consents-vault/restricted/', views.consent_audit_vault, name='consent_audit_vault'),
    path('api/log/', views.agent_log_receiver, name='agent_log_receiver'),
    path('api/agent-live-data/<int:agent_id>/', views.fetch_agent_live_data, name='fetch_agent_live_data'),
    path('api/agents-live-status/', views.agents_live_status, name='agents_live_status'),
    path('api/command/ajax/', views.queue_command_ajax, name='queue_command_ajax'),
    path('api/campaign/create/', views.create_test_campaign, name='create_test_campaign'),
    path('campaign/<int:campaign_id>/', views.campaign_dashboard, name='campaign_dashboard'),
    path('api/honeytoken/trigger/', views.honeytoken_trigger, name='honeytoken_trigger'),
    path('api/campaign/<int:campaign_id>/action/', views.campaign_action, name='campaign_action'),
    path('api/campaign/<int:campaign_id>/logs/', views.campaign_live_logs, name='campaign_live_logs'),
    path('campaigns/manage/', views.campaign_management, name='campaign_management'),
    path('api/ai_leak/trigger/', views.ai_leak_trigger, name='api_ai_leak_trigger'),
]
