from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import LDAPConfiguration, AdminConsentLog, Employee
from django.http import JsonResponse
from .utils import perform_ldap_sync
from django.contrib.auth import logout
from django.contrib.auth import update_session_auth_hash
from behavioral.models import SystemNotification, AgentCampaignRisk, AgentLog, Agent
from django.db.models import Avg, Max

def landing_view(request):
    return render(request, 'core/landing_page.html')



def deployment_hub_view(request):
    # Make sure your actual HTML file is named exactly like this!
    return render(request, 'core/deployment_hub.html') 

def ui_kit_view(request):
    return render(request, 'core/ui_kit.html')

def dataviz_kit_view(request):
    return render(request, 'core/dataviz-kit.html')

def login_view(request):
    if request.user.is_authenticated:
        return redirect('deployment')
    
    if request.method == 'POST':
        email_input = request.POST.get('email')
        password_input = request.POST.get('password')

        user = authenticate(request, email=email_input, password=password_input)
        if user is not None:
            login(request, user)

            if not Employee.objects.exists():
                return redirect('ldap_setup')
            
            return redirect('deployment')
        else:
            messages.error(request, "Invalid security credentials")
    return render(request, 'core/login.html')    

@login_required(login_url='login')
def ldap_setup(request):
    if Employee.objects.exists():
        return redirect('deployment')

    if request.method == 'POST':
        # 1. Capture the Evidence
        consent_flag = request.POST.get('consent_given') == 'true'
        
        if consent_flag:
            # Capture the IP address for the audit log
            client_ip = request.META.get('HTTP_X_FORWARDED_FOR')
            if client_ip:
                client_ip = client_ip.split(',')[0]
            else:
                client_ip = request.META.get('REMOTE_ADDR')

            AdminConsentLog.objects.create(
                admin=request.user,
                consent_given=True,
                ip_address=client_ip
            )

        # 2. Capture and Save LDAP Config
        LDAPConfiguration.objects.update_or_create(
            id=1, 
            defaults={
                'server_ip': request.POST.get('server_ip'),
                'port': request.POST.get('port'),
                'bind_dn': request.POST.get('bind_dn'),
                'bind_password': request.POST.get('bind_password'),
                'base_ou': request.POST.get('base_ou'),
                'is_configured': True
            }
        )
        
        return redirect('ldap_sync_loading')

    return render(request, 'core/ldap_setup.html')

@login_required(login_url='login')
def ldap_sync_loading(request):
    return render(request, 'core/ldap_loading.html')

@login_required(login_url='login')
def execute_ldap_sync(request):
    """AJAX endpoint triggered by the loading screen to run the extraction."""
    if request.method == "POST":
        result = perform_ldap_sync()
        return JsonResponse(result)
    
    return JsonResponse({"success": False, "error": "Invalid request method."})


@login_required(login_url='login')
def system_settings(request):
    return render(request, 'core/settings.html')

@login_required(login_url='login')
def admin_logout(request):
    logout(request)
    return redirect('login')

@login_required(login_url='login')
def system_settings(request):
    if request.method == 'POST':
        
        # 1. Traitement du Formulaire de Profil
        if 'update_profile' in request.POST:
            new_username = request.POST.get('username')
            new_email = request.POST.get('email')
            
            # Mise à jour si les champs ne sont pas vides
            if new_email:
                request.user.email = new_email
            if new_username:
                request.user.username = new_username
                
            request.user.save()
            messages.success(request, "Les informations du compte ont été mises à jour.")
            return redirect('settings')
            
        # 2. Traitement du Formulaire de Mot de Passe
        elif 'update_password' in request.POST:
            old_password = request.POST.get('old_password')
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')
            
            # Vérifications de sécurité
            if not request.user.check_password(old_password):
                messages.error(request, "L'ancien mot de passe est incorrect.")
            elif new_password != confirm_password:
                messages.error(request, "Les nouveaux mots de passe ne correspondent pas.")
            elif len(new_password) < 12: # Ajout d'une petite vérification de base
                messages.error(request, "Le mot de passe doit contenir au moins 12 caractères.")
            else:
                # Tout est bon, on chiffre et on sauvegarde
                request.user.set_password(new_password)
                request.user.save()
                # Garde l'administrateur connecté !
                update_session_auth_hash(request, request.user)
                messages.success(request, "Le mot de passe a été modifié avec succès.")
                
            return redirect('settings')

    return render(request, 'core/settings.html')

@login_required(login_url='login')
def notifications(request):
    behavioral_notifs = SystemNotification.objects.all().order_by('-created_at')
    
    context = {
        'notifications': behavioral_notifs
    }
    return render(request, 'core/notifications.html', context)

@login_required(login_url='login')
def directory(request):
    if request.method == 'POST':
        emp_id = request.POST.get('employee_id')
        action = request.POST.get('action')
        emp = get_object_or_404(Employee, id=emp_id)
        
        if action == 'delete':
            emp.delete()
            messages.success(request, f"L'employé {emp.full_name} a été retiré de l'annuaire.")
        elif action == 'edit':
            emp.department = request.POST.get('department')
            emp.status = request.POST.get('status')
            emp.save()
            messages.success(request, f"Profil de {emp.full_name} mis à jour.")
        return redirect('directory')

    employees = Employee.objects.all().order_by('full_name')
    return render(request, 'core/directory.html', {'employees': employees})

 
@login_required(login_url='login')
def ldap_management(request):
    # Récupérer la config actuelle (on suppose qu'il n'y en a qu'une, ID=1)
    config = LDAPConfiguration.objects.first()
    # Récupérer l'historique des consentements (audit log)
    logs = AdminConsentLog.objects.all().order_by('-timestamp')[:10] # Les 10 derniers

    if request.method == 'POST':
        action = request.POST.get('action')
        
        # Action 1 : L'admin modifie la configuration via la modale
        if action == 'update_config':
            password_confirm = request.POST.get('admin_password')
            
            # Sécurité : Vérifier le mot de passe de l'admin actuel avant d'autoriser la modif
            if not request.user.check_password(password_confirm):
                messages.error(request, "Mot de passe administrateur incorrect. Configuration non modifiée.")
            else:
                LDAPConfiguration.objects.update_or_create(
                    id=1, 
                    defaults={
                        'server_ip': request.POST.get('server_ip'),
                        'port': request.POST.get('port'),
                        'bind_dn': request.POST.get('bind_dn'),
                        'bind_password': request.POST.get('bind_password'),
                        'base_ou': request.POST.get('base_ou'),
                        'is_configured': True
                    }
                )
                messages.success(request, "Configuration LDAP mise à jour avec succès.")
            return redirect('ldap_management')

        # Action 2 : L'admin relance une synchronisation manuelle
        elif action == 'resync':
            # On enregistre une nouvelle preuve de consentement (Audit Trail)
            client_ip = request.META.get('HTTP_X_FORWARDED_FOR')
            if client_ip:
                client_ip = client_ip.split(',')[0]
            else:
                client_ip = request.META.get('REMOTE_ADDR')

            AdminConsentLog.objects.create(
                admin=request.user,
                consent_given=True,
                ip_address=client_ip
            )
            # On le redirige vers votre page de chargement existante !
            return redirect('ldap_sync_loading')

    return render(request, 'core/ldap_management.html', {
        'config': config,
        'logs': logs
    })

def documentation(request):
    return render(request, 'core/documentation.html')