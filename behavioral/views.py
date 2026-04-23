import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Q
from core.models import Employee
from .models import Agent, DeploymentConsentLog, AgentCommand, AgentLog
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import os
from django.conf import settings
from django.http import FileResponse, HttpResponseForbidden, Http404
from django.views.decorators.http import require_GET
from django.contrib import messages

@login_required(login_url='login')
def dashboard(request):
    all_agents = Agent.objects.select_related('employee').all()
    
    # 1. LIMIT TO 5 RECENT/CRITICAL AGENTS FOR THE DASHBOARD
    # Orders by compromised first, then by newest
    display_agents = all_agents.order_by('status', '-created_at')[:5]
    
    # 2. FILTER EMPLOYEES: Don't show employees who already have a 'Pending' agent
    pending_employee_ids = all_agents.filter(status='Pending').values_list('employee_id', flat=True)
    available_employees = Employee.objects.exclude(id__in=pending_employee_ids).order_by('full_name')
    
    # Metrics
    total_agents = all_agents.count()
    online_agents = sum(1 for agent in all_agents if agent.is_online_realtime)
    compromised_agents = all_agents.filter(status='Compromised').count()
    offline_agents = total_agents - online_agents
    
    context = {
        'agents': display_agents, # Only 5 agents
        'employees': available_employees, # Filtered list
        'metrics': {
            'total': total_agents,
            'online': online_agents,
            'compromised': compromised_agents,
            'offline': offline_agents
        }
    }
    
    return render(request, 'behavioral/dashboard.html', context)
    return render(request, 'behavioral/dashboard.html', context)

@login_required(login_url='login')
@require_POST
def generate_agent(request):
    try:
        data = json.loads(request.body)
        employee_id = data.get('employee_id')
        consent = data.get('consent')

        if not consent:
            return JsonResponse({'success': False, 'error': "Le consentement légal est requis."})

        employee = Employee.objects.get(id=employee_id)

        # 1. Création de l'agent
        agent = Agent.objects.create(
            employee=employee,
            status='Pending'
        )

        # 2. NOUVEAU : Sauvegarde de la preuve de consentement (Non-Répudiation)
        client_ip = request.META.get('HTTP_X_FORWARDED_FOR')
        if client_ip:
            client_ip = client_ip.split(',')[0]
        else:
            client_ip = request.META.get('REMOTE_ADDR')

        DeploymentConsentLog.objects.create(
            admin=request.user,
            target_employee=employee,
            agent_token=agent.token,
            ip_address=client_ip
        )

        # 3. Renvoie le token à l'interface
        return JsonResponse({
            'success': True,
            'token': str(agent.token)
        })

    except Employee.DoesNotExist:
        return JsonResponse({'success': False, 'error': "Employé introuvable."})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    
# --- À AJOUTER POUR L'AJAX DES COMMANDES C2 ---
@login_required(login_url='login')
@require_POST
def queue_command_ajax(request):
    """ Reçoit les ordres C2 depuis la modale sans recharger la page """
    try:
        data = json.loads(request.body)
        agent_id = data.get('agent_id')
        cmd = data.get('command')
        
        agent = Agent.objects.get(id=agent_id)
        
        if agent.status == 'Pending':
            return JsonResponse({'success': False, 'error': "Impossible d'envoyer un ordre à un agent inactif."})
            
        AgentCommand.objects.create(agent_id=agent_id, command=cmd)
        return JsonResponse({'success': True, 'message': f"Ordre '{cmd}' envoyé avec succès."})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# --- À REMPLACER POUR CORRIGER LE CONSENTEMENT ---
@csrf_exempt
@require_POST
def agent_register(request):
    """ Point d'entrée pour la première installation de l'agent """
    try:
        data = json.loads(request.body)
        token = data.get('token')
        hostname = data.get('hostname', 'Machine Inconnue')

        agent = Agent.objects.get(token=token)

        client_ip = request.META.get('HTTP_X_FORWARDED_FOR')
        if client_ip:
            client_ip = client_ip.split(',')[0]
        else:
            client_ip = request.META.get('REMOTE_ADDR')

        # Mise à jour des infos de base
        agent.hostname = hostname
        agent.ip_address = client_ip
        agent.status = 'Online'
        agent.last_heartbeat = timezone.now()
        
        # CORRECTION DU CONSENTEMENT ICI
        if data.get('user_consent') == True:
            agent.user_consent_granted = True
            agent.user_consent_timestamp = timezone.now()
            
        agent.save()

        return JsonResponse({'success': True, 'message': 'Agent enregistré.'})
    except Agent.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Jeton invalide.'}, status=401)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
@login_required(login_url='login')
def agent_management(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        agent_id = request.POST.get('agent_id')
        
        if action == 'revoke' and agent_id:
            Agent.objects.filter(id=agent_id).delete()
            messages.success(request, "L'agent a été révoqué et supprimé du système.")
            return redirect('behavioral:agent_management')
            
        # NOUVEAU : Mise en file d'attente d'une commande C2
        elif action == 'queue_command' and agent_id:
            cmd = request.POST.get('command')
            AgentCommand.objects.create(agent_id=agent_id, command=cmd)
            messages.success(request, f"L'ordre '{cmd}' a été mis en attente pour l'agent.")
            return redirect('behavioral:agent_management')

    agents = Agent.objects.select_related('employee').all().order_by('-created_at')
    return render(request, 'behavioral/agent_management.html', {'agents': agents})

@login_required(login_url='login')
def fetch_agent_live_data(request, agent_id):
    """ Récupère les logs ET l'état en temps réel pour la Modale (sur clic du bouton rafraichir) """
    try:
        agent = Agent.objects.get(id=agent_id)
        logs = AgentLog.objects.filter(agent=agent).order_by('-timestamp')[:30]
        
        # Formatage des logs
        logs_data = [{
            'timestamp': log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            'level': log.level,
            'message': log.message
        } for log in logs]

        # Détermination du vrai statut
        current_status = agent.status
        if current_status != 'Compromised':
            current_status = 'Online' if agent.is_online_realtime else ('Pending' if current_status == 'Pending' else 'Offline')

        return JsonResponse({
            'success': True,
            'ip': agent.ip_address or "-",
            'consent': agent.user_consent_granted,
            'status': current_status,
            'logs': logs_data
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required(login_url='login')
def agents_live_status(request):
    """ API légère pour mettre à jour le tableau principal en arrière-plan """
    agents = Agent.objects.all()
    data = {}
    for agent in agents:
        current_status = agent.status
        if current_status != 'Compromised':
            current_status = 'Online' if agent.is_online_realtime else ('Pending' if current_status == 'Pending' else 'Offline')
            
        data[agent.id] = {
            'ip': agent.ip_address or "-",
            'status': current_status
        }
    return JsonResponse({'agents': data})

# NOUVEAU : API pour que l'agent envoie ses logs
@csrf_exempt
@require_POST
def agent_log_receiver(request):
    try:
        data = json.loads(request.body)
        agent = Agent.objects.get(token=data.get('token'))
        AgentLog.objects.create(
            agent=agent,
            level=data.get('level', 'INFO'),
            message=data.get('message')
        )
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False}, status=400)

# MISE À JOUR : Le Heartbeat distribue maintenant les commandes !
@csrf_exempt
@require_POST
def agent_heartbeat(request):
    try:
        data = json.loads(request.body)
        token = data.get('token')
        agent = Agent.objects.get(token=token)
        
        agent.last_heartbeat = timezone.now()
        if agent.status == 'Offline' or agent.status == 'Pending':
            agent.status = 'Online'
        agent.save()

        # Récupère les commandes non exécutées
        pending_cmds = AgentCommand.objects.filter(agent=agent, is_executed=False)
        command_list = [cmd.command for cmd in pending_cmds]
        
        # Marque comme lu
        pending_cmds.update(is_executed=True)

        return JsonResponse({'success': True, 'commands': command_list})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    

@require_GET
def download_agent(request):
    """ Endpoint sécurisé appelé par le script PowerShell de la cible """
    token = request.GET.get('token')
    
    if not token:
        return HttpResponseForbidden("Jeton d'autorisation manquant.")
        
    try:
        # Vérification : Le jeton correspond-il à un agent en attente ?
        agent = Agent.objects.get(token=token)
        
        # Optionnel : Vous pourriez ajouter ici un log "Téléchargement initié par l'IP X"
        
        # Chemin vers le fichier exécutable sécurisé
        file_path = os.path.join(settings.BASE_DIR, 'protected_media', 'agent.exe')
        
        if os.path.exists(file_path):
            # FileResponse lit le fichier en streaming (très efficace pour la mémoire)
            return FileResponse(open(file_path, 'rb'), as_attachment=True, filename='psyche_agent.exe')
        else:
            raise Http404("Le fichier de l'agent n'est pas disponible sur le serveur.")
            
    except Agent.DoesNotExist:
        return HttpResponseForbidden("Jeton d'autorisation invalide ou expiré.")
    
@login_required(login_url='login')
def agent_management(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        agent_id = request.POST.get('agent_id')
        
        if action == 'revoke' and agent_id:
            Agent.objects.filter(id=agent_id).delete()
            messages.success(request, "L'agent a été révoqué et supprimé du système.")
            return redirect('behavioral:agent_management')
            
        # NOUVEAU : Mise en file d'attente d'une commande C2
        elif action == 'queue_command' and agent_id:
            cmd = request.POST.get('command')
            AgentCommand.objects.create(agent_id=agent_id, command=cmd)
            messages.success(request, f"L'ordre '{cmd}' a été mis en attente pour l'agent.")
            return redirect('behavioral:agent_management')

    agents = Agent.objects.select_related('employee').all().order_by('-created_at')
    return render(request, 'behavioral/agent_management.html', {'agents': agents})

# NOUVEAU : API pour récupérer les logs dans l'interface (AJAX)
@login_required(login_url='login')
def fetch_agent_logs(request, agent_id):
    logs = AgentLog.objects.filter(agent_id=agent_id).order_by('-timestamp')[:30] # 30 derniers logs
    logs_data = [{
        'timestamp': log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        'level': log.level,
        'message': log.message
    } for log in logs]
    return JsonResponse({'logs': logs_data})

# NOUVEAU : API pour que l'agent envoie ses logs
@csrf_exempt
@require_POST
def agent_log_receiver(request):
    try:
        data = json.loads(request.body)
        agent = Agent.objects.get(token=data.get('token'))
        AgentLog.objects.create(
            agent=agent,
            level=data.get('level', 'INFO'),
            message=data.get('message')
        )
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False}, status=400)

# MISE À JOUR : Le Heartbeat distribue maintenant les commandes !
@csrf_exempt
@require_POST
def agent_heartbeat(request):
    try:
        data = json.loads(request.body)
        token = data.get('token')
        agent = Agent.objects.get(token=token)
        
        agent.last_heartbeat = timezone.now()
        if agent.status == 'Offline' or agent.status == 'Pending':
            agent.status = 'Online'
        agent.save()

        # Récupère les commandes non exécutées
        pending_cmds = AgentCommand.objects.filter(agent=agent, is_executed=False)
        command_list = [cmd.command for cmd in pending_cmds]
        
        # Marque comme lu
        pending_cmds.update(is_executed=True)

        return JsonResponse({'success': True, 'commands': command_list})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required(login_url='login')
def consent_audit_vault(request):
    """ 
    URL CACHÉE : Registre légal des consentements utilisateurs finaux.
    Accessible uniquement en tapant l'URL manuellement.
    """
    # On ne récupère que les agents où l'utilisateur a explicitement cliqué sur "Accepter"
    consents = Agent.objects.filter(user_consent_granted=True).select_related('employee').order_by('-user_consent_timestamp')
    
    return render(request, 'behavioral/consent_vault.html', {'consents': consents})