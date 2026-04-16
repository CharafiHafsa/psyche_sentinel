from django.urls import path
from . import views

urlpatterns = [
    # Leave this empty so it loads immediately at 127.0.0.1:8000/
    path('', views.landing_view, name='landing'), 
    
    path('login/', views.login_view, name='login'),
    path('setup/directory/', views.ldap_setup, name='ldap_setup'),
    path('setup/syncing/', views.ldap_sync_loading, name='ldap_sync_loading'),
    path('api/execute-sync/', views.execute_ldap_sync, name='execute_ldap_sync'),
    path('deployment/', views.deployment_hub_view, name='deployment'),
    path('settings/', views.system_settings, name='settings'),
    path('ui-kit/', views.ui_kit_view, name='ui-kit'),
    path('dataviz-kit/', views.dataviz_kit_view, name='dataviz-kit'),
    path('notifications/', views.notifications, name='notifications'),
    path('directory/', views.employee_directory, name='directory'),
    path('ldap/management/', views.ldap_management, name='ldap_management'),
    path('logout/', views.admin_logout, name='logout'),
]