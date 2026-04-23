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
]
