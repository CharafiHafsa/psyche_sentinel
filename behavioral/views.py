import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Q
from core.models import Employee
from .models import Agent, DeploymentConsentLog, AgentCommand, AgentLog, TestCampaign, SimulationModule, HoneytokenTemplate, HoneytokenInstance, SystemNotification, AILeakAlert
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import os
from django.conf import settings
from django.http import FileResponse, HttpResponseForbidden, Http404
from django.views.decorators.http import require_GET
from django.contrib import messages
from django.urls import reverse
import random
from django.shortcuts import get_object_or_404
from datetime import timedelta
from django.db.models import Max, Avg, Sum
from django.db.models import Count

def calculate_honeytoken_risk(campaign, total_agents):
    """ Calcule le score de risque basé sur la nouvelle formule avancée """
    if total_agents == 0:
        return {'score': 0, 'label': 'LOW', 'color': 'var(--color-success)', 'exposure': 0, 'behavior': 0, 'impact': 0}

    instances = HoneytokenInstance.objects.filter(campaign=campaign)
    triggered = instances.filter(triggered=True)

    if not triggered.exists():
        return {'score': 0, 'label': 'LOW', 'color': 'var(--color-success)', 'exposure': 0, 'behavior': 0, 'impact': 0}

    # 1. Exposure (0-100) : % d'agents compromis
    compromised_agents = triggered.values('agent').distinct().count()
    exposure = (compromised_agents / total_agents) * 100

    # 2. Behavior (0-100)
    # Gravité Max possible par événement = 5 (Sensibilité) * 2.0 (Action Delete) = 10
    total_severity = triggered.aggregate(Sum('highest_severity'))['highest_severity__sum'] or 0.0
    max_possible = total_agents * 10 
    behavior = (total_severity / max_possible) * 100 if max_possible > 0 else 0
    behavior = min(behavior, 100)

    # 3. Impact (0-100) : Moyenne lissée
    avg_severity = triggered.aggregate(Avg('highest_severity'))['highest_severity__avg'] or 0.0
    impact = (float(avg_severity) / 10) * 100
    impact = min(impact, 100)

    # Formule Finale
    risk_score = (0.4 * exposure) + (0.3 * behavior) + (0.3 * impact)
    score_val = min(100, int(risk_score))

    label, color = "LOW", "var(--color-success)"
    if score_val > 20: label, color = "MEDIUM", "#eab308"
    if score_val > 50: label, color = "HIGH", "var(--color-warning)"
    if score_val > 80: label, color = "CRITICAL", "var(--color-danger)"

    return {
        'score': score_val,
        'label': label,
        'color': color,
        'exposure': int(exposure),
        'behavior': int(behavior),
        'impact': int(impact)
    }

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

    departments = Employee.objects.exclude(department__isnull=True).exclude(department__exact='').values_list('department', flat=True).distinct()
    modules = SimulationModule.objects.all()

    recent_campaigns = TestCampaign.objects.filter(is_deleted=False).order_by('-created_at')[:5]
    context = {
        'agents': display_agents, # Only 5 agents
        'employees': available_employees, # Filtered list
        'departments': departments,
        'modules': modules,
        'recent_campaigns': recent_campaigns,
        'metrics': {
            'total': total_agents,
            'online': online_agents,
            'compromised': compromised_agents,
            'offline': offline_agents
        }
    }
    
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
        
        # Mise à jour du statut
        agent.last_heartbeat = timezone.now()
        if agent.status == 'Offline' or agent.status == 'Pending':
            agent.status = 'Online'
        agent.save()

        # --- CORRECTION ICI : On ne récupère que les commandes dont l'heure est arrivée ! ---
        now = timezone.now()
        pending_cmds = AgentCommand.objects.filter(
            agent=agent, 
            is_executed=False, 
            execute_at__lte=now  # "lte" = Less Than or Equal (Inférieur ou égal à maintenant)
        )
        
        command_list = []
        for cmd in pending_cmds:
            command_list.append({
                'command' : cmd.command,
                'payload' : cmd.payload
            })
        
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

def _deploy_honeytoken_module(campaign, active_agents, total_minutes):
    """ Gère la logique complexe de déploiement des leurres avec Jitter et Poids """
    t_hours = total_minutes / 60.0 
    rotation_enabled = t_hours > 48 
    w_hours = min(48.0, t_hours / 3.0) if rotation_enabled else t_hours

    for agent in active_agents:
        dept = agent.employee.department.lower() if agent.employee.department else 'all'
        templates = HoneytokenTemplate.objects.filter(Q(department__iexact=dept) | Q(department__iexact='all'))
        
        if templates.exists():
            templates_list = list(templates)
            n_tokens = random.choices([1, 2], weights=[0.8, 0.2])[0]
            
            for _ in range(n_tokens):
                weights = [6 - t.data_sensitivity for t in templates_list]
                chosen_template = random.choices(templates_list, weights=weights)[0]
                
                dir_choices = ['DESKTOP', 'DOCUMENTS', 'DOWNLOADS']
                chosen_dir = random.choices(dir_choices, weights=[0.5, 0.4, 0.1])[0]
                
                # Jitter calculé côté Serveur
                max_jitter_hours = min(6.0, w_hours / 2.0)
                delay_seconds = int(random.uniform(0, max_jitter_hours) * 3600)
                execution_time = timezone.now() + timezone.timedelta(seconds=delay_seconds)
                
                # Création de l'instance pour le suivi
                instance = HoneytokenInstance.objects.create(
                    agent=agent,
                    template=chosen_template,
                    campaign=campaign,
                    file_path="En attente de déploiement (Jitter actif)..."
                )

                payload = {
                    "instance_id": instance.id,
                    "file_name": chosen_template.file_name,
                    "extension": chosen_template.file_extension,
                    "directory": chosen_dir,
                    "content": chosen_template.fake_content,
                    "lifespan_hours": w_hours if rotation_enabled else 0
                }
                
                # UN SEUL CREATE ! Avec le Jitter
                AgentCommand.objects.create(
                    agent=agent,
                    command='DEPLOY_HONEYTOKEN',
                    payload=payload,
                    execute_at=execution_time 
                )


def _deploy_ai_leak_module(active_agents):
    """ Ordonne aux agents de démarrer le keylogger éthique """
    for agent in active_agents:
        AgentCommand.objects.create(
            agent=agent,
            command='START_AI_MONITOR',
            payload={} # Pas besoin de payload complexe pour l'instant
        )
@login_required(login_url='login')
def create_test_campaign(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            module_ids = data.get('modules', [])
            target_dept = data.get('target_department')
            
            if not module_ids:
                return JsonResponse({'success': False, 'error': "Veuillez sélectionner au moins un vecteur d'attaque."})

            dur_val = int(data.get('duration_val', 0))
            dur_unit = data.get('duration_unit', 'days')
            multipliers = {'minutes': 1, 'hours': 60, 'days': 1440, 'weeks': 10080, 'months': 43200}
            total_minutes = dur_val * multipliers.get(dur_unit, 1440)

            is_scheduled = data.get('is_scheduled') == 'True'
            scheduled_date = parse_datetime(data.get('scheduled_date')) if is_scheduled else None

            campaign = TestCampaign.objects.create(
                target_department=target_dept,
                duration_minutes=total_minutes,
                is_scheduled=is_scheduled,
                scheduled_for=scheduled_date
            )
            campaign.modules.set(module_ids)
            
            warnings = []
            if target_dept == 'ALL':
                target_employees = Employee.objects.all()
            else:
                target_employees = Employee.objects.filter(department=target_dept)
                
            active_agents = Agent.objects.filter(employee__in=target_employees).exclude(status='Pending')    
            missing_agents_count = target_employees.exclude(id__in=active_agents.values_list('employee_id', flat=True)).count()

            if missing_agents_count > 0:
                warnings.append(f"{missing_agents_count} employé(s) ciblés n'ont pas d'agent actif. Le test les ignorera pour l'instant.")

            # --- ROUTAGE DES MODULES ---
            modules = SimulationModule.objects.filter(id__in=module_ids)
            for module in modules:
                if module.code == 'HONEYTOKEN':
                    _deploy_honeytoken_module(campaign, active_agents, total_minutes)
                elif module.code == 'AI_LEAK':
                    _deploy_ai_leak_module(active_agents)

            redirect_url = reverse('behavioral:campaign_dashboard', args=[campaign.id])
            return JsonResponse({'success': True, 'redirect_url': redirect_url, 'warnings': warnings})
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Méthode non autorisée'})


@csrf_exempt
@require_POST
def honeytoken_trigger(request):
    """ API appelée par l'agent quand un leurre est manipulé """
    try:
        data = json.loads(request.body)
        token = data.get('token')
        instance_id = data.get('instance_id')
        action = data.get('action') # ex: OPEN, MODIFY, DELETE

        agent = Agent.objects.get(token=token)
        instance = HoneytokenInstance.objects.get(id=instance_id, agent=agent)

        now = timezone.now()

        # 1. Gestion des Timestamps et du Time Factor (Forensics)
        if not instance.first_triggered_at:
            instance.first_triggered_at = now
            # Calcul du temps mis par la cible pour tomber dans le piège (en secondes)
            delta = (now - instance.created_at).total_seconds()
            instance.time_to_trigger_seconds = int(delta)

        instance.triggered = True
        instance.triggered_at = now # Met à jour la date de dernière interaction

        # 2. Gestion de la Séquence d'Actions (Action Sequence)
        sequence = instance.action_sequence
        # On évite d'ajouter 50 fois "OPEN" si le système bégaye, on n'ajoute que si l'action est nouvelle/différente
        if not sequence or sequence[-1] != action:
            sequence.append(action)
            instance.action_sequence = sequence

        instance.save()
        
        # 3. Recalcul de la gravité en fonction des nouvelles actions
        instance.update_severity()

        # 4. Création d'un Log d'Alerte pour le flux en direct
        AgentLog.objects.create(
            agent=agent,
            level='ALERT',
            message=f"🍯 PIÈGE TOUCHÉ ! Action '{action}' détectée sur '{instance.template.file_name}'. Séquence actuelle : {sequence}"
        )

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    
@csrf_exempt
@require_POST
def ai_leak_trigger(request):
    """ API appelée par l'agent quand une fuite de données (DLP) est détectée """
    try:
        data = json.loads(request.body)
        token = data.get('token')
        
        ai_platform = data.get('ai_platform', 'Inconnu')
        data_type = data.get('data_type', 'UNKNOWN')
        length = data.get('length', 0)
        severity = data.get('severity', 1)
        action = data.get('action', 'PASTE')

        agent = Agent.objects.get(token=token)
        
        # On trouve la campagne AI_LEAK actuellement en cours
        campaign = TestCampaign.objects.filter(status='Running', modules__code='AI_LEAK').last()
        
        if not campaign:
            return JsonResponse({'success': False, 'error': 'Aucune campagne AI_LEAK active trouvée.'})

        # 1. Enregistrement de la fuite
        AILeakAlert.objects.create(
            agent=agent,
            campaign=campaign,
            ai_platform=ai_platform,
            data_type_detected=data_type,
            clipboard_length=length,
            action_type=action,
            severity=severity
        )

        # 2. Création d'un Log d'Alerte pour le flux en direct
        AgentLog.objects.create(
            agent=agent,
            level='CRITICAL' if severity >= 4 else 'WARNING',
            message=f"🧠 SHADOW AI : Fuite '{data_type}' ({length} caractères) vers {ai_platform}."
        )

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    

@login_required(login_url='login')
def campaign_dashboard(request, campaign_id):
    # On bloque l'accès si la campagne est supprimée
    campaign = get_object_or_404(TestCampaign, id=campaign_id, is_deleted=False)
    modules = campaign.modules.all()
    module_codes = [m.code for m in modules]

    # --- 1. PÉRIMÈTRE ET COUVERTURE ---
    if campaign.target_department == 'ALL':
        target_employees = Employee.objects.all()
    else:
        target_employees = Employee.objects.filter(department=campaign.target_department)

    total_targets = target_employees.count()
    campaign_agents = Agent.objects.filter(employee__in=target_employees)
    active_agents = campaign_agents.exclude(status='Pending')
    active_employees_ids = active_agents.values_list('employee_id', flat=True)

    pending_agents = Agent.objects.filter(employee__in=target_employees, status='Pending')
    pending_employees_ids = pending_agents.values_list('employee_id', flat=True)

    no_agent_employees = target_employees.exclude(id__in=active_employees_ids).exclude(id__in=pending_employees_ids)

    active_count = active_agents.count()
    pending_count = pending_agents.count()
    no_agent_count = no_agent_employees.count()

    vulnerable_targets_count = pending_count + no_agent_count

    coverage_percent = int((active_count / total_targets * 100)) if total_targets > 0 else 0

    # --- 2. GESTION DU TEMPS ---
    effective_duration = campaign.duration_minutes + campaign.total_paused_minutes
    end_time = campaign.created_at + timedelta(minutes=effective_duration)
    
    if campaign.status == 'Paused' and campaign.last_paused_at:
        current_pause = (timezone.now() - campaign.last_paused_at).total_seconds() / 60.0
        end_time += timedelta(minutes=current_pause)

    time_remaining = end_time - timezone.now()
    is_expired = time_remaining.total_seconds() <= 0
    
    if is_expired and campaign.status == 'Running':
        campaign.status = 'Completed'
        campaign.save()

    total_seconds = (campaign.duration_minutes + campaign.total_paused_minutes) * 60
    elapsed_seconds = (timezone.now() - campaign.created_at).total_seconds()
    if campaign.status == 'Paused' and campaign.last_paused_at:
         elapsed_seconds -= (timezone.now() - campaign.last_paused_at).total_seconds()

    progress_percent = min(100, int((elapsed_seconds / total_seconds) * 100)) if not is_expired else 100

    # --- 3. DÉTAILS, RISQUES ET ANALYSE HONEYTOKEN ---
    honeytoken_stats = {}
    instances = []
    
    # Valeurs par défaut globales
    risk_data = {'score': 0, 'label': 'LOW', 'color': 'var(--color-success)', 'exposure': 0, 'behavior': 0, 'impact': 0}
    action_counts = {'OPEN': 0, 'MODIFY': 0, 'DELETE': 0}
    destructive_count = 0
    dept_triggers = {}
    reliability_level = "HIGH"
    reliability_color = "var(--color-success)"

    if 'HONEYTOKEN' in module_codes:
        instances = HoneytokenInstance.objects.filter(campaign=campaign).select_related('agent', 'template')
        triggered_instances = instances.filter(triggered=True)
        deployed_real_count = instances.exclude(file_path__icontains="En attente").count()

        honeytoken_stats = {
            'expected': instances.count(),
            'deployed_real': deployed_real_count,
            'triggered': triggered_instances.count(),
            'safe': instances.filter(triggered=False).count(),
        }

        # Calcul du Risque
        if active_agents.count() > 0:
            risk_data = calculate_honeytoken_risk(campaign, active_agents.count())

            # Analyse Comportementale
            for inst in triggered_instances:
                if inst.action_sequence:
                    for action in inst.action_sequence:
                        if action in action_counts:
                            action_counts[action] += 1
                            
                    if 'MODIFY' in inst.action_sequence or 'DELETE' in inst.action_sequence:
                        destructive_count += 1
                
                dept = inst.agent.employee.department
                dept_triggers[dept] = dept_triggers.get(dept, 0) + 1

    # --- 4. MODULE SHADOW AI (DLP) ---
    ai_alerts = []
    ai_stats = {'total': 0, 'critical': 0, 'top_platform': 'N/A'}
    
    if 'AI_LEAK' in module_codes:
        ai_alerts = AILeakAlert.objects.filter(campaign=campaign).order_by('-timestamp')
        
        if ai_alerts.exists():
            # Plateforme la plus utilisée
            top_platform = ai_alerts.values('ai_platform').annotate(count=Count('id')).order_by('-count').first()
            
            ai_stats = {
                'total': ai_alerts.count(),
                'critical': ai_alerts.filter(severity__gte=4).count(),
                'top_platform': top_platform['ai_platform'] if top_platform else 'N/A'
            }
    # 4. Évaluation de la fiabilité (Reliability) en dehors du bloc Honeytoken car ça concerne la couverture globale
    if coverage_percent < 40:
        reliability_level = "LOW"
        reliability_color = "var(--color-danger)"
    elif coverage_percent < 70:
        reliability_level = "MEDIUM"
        reliability_color = "var(--color-warning)"

    # --- 5. CONSTRUCTION DU CONTEXTE ---
    context = {
        'campaign': campaign,
        'modules': modules,
        'module_codes': module_codes,
        'total_targets': total_targets,
        'active_agents': active_agents,
        'active_count': active_count,
        'pending_count': pending_count,
        'no_agent_count': no_agent_count,
        'vulnerable_targets_count': vulnerable_targets_count,
        'no_agent_employees': no_agent_employees,
        'pending_agents': pending_agents,
        'active_agents_list': active_agents,
        'coverage_percent': coverage_percent,
        'end_time': end_time,
        'progress_percent': progress_percent,
        'is_expired': is_expired,
        
        # Données de Risque & Fiabilité
        'risk_data': risk_data,
        'reliability_level': reliability_level,
        'reliability_color': reliability_color,
        
        # Données Honeytoken (Analyse)
        'honeytoken_stats': honeytoken_stats,
        'instances': instances,
        'action_counts': action_counts,
        'destructive_count': destructive_count,
        'dept_triggers': dept_triggers,

        'ai_alerts': ai_alerts,
        'ai_stats': ai_stats,
    }
    
    return render(request, 'behavioral/campaign_dashboard.html', context)

@login_required(login_url='login')
@require_POST
def campaign_action(request, campaign_id):
    try:
        data = json.loads(request.body)
        action = data.get('action')
        campaign = get_object_or_404(TestCampaign, id=campaign_id)
        
        # 1. Identifier les agents concernés par cette campagne
        if campaign.target_department == 'ALL':
            active_agents = Agent.objects.exclude(status='Pending')
        else:
            active_agents = Agent.objects.filter(employee__department=campaign.target_department).exclude(status='Pending')

        # 2. Traitement des actions
        if action == 'PAUSE' and campaign.status == 'Running':
            campaign.status = 'Paused'
            campaign.last_paused_at = timezone.now()
            campaign.save()
            SystemNotification.objects.create(title="Campagne en Pause", message=f"{campaign.name} a été suspendue.", type="WARNING")
            
            # Ordre C2
            for agent in active_agents:
                AgentCommand.objects.create(agent=agent, command='PAUSE_CAMPAIGN')
            
        elif action == 'RESUME' and campaign.status == 'Paused':
            campaign.status = 'Running'
            pause_dur = (timezone.now() - campaign.last_paused_at).total_seconds() / 60.0
            campaign.total_paused_minutes += int(pause_dur)
            campaign.last_paused_at = None
            campaign.save()
            
            # Ordre C2
            for agent in active_agents:
                AgentCommand.objects.create(agent=agent, command='RESUME_CAMPAIGN')
            
        elif action == 'STOP':
            campaign.status = 'Completed'
            campaign.save()
            SystemNotification.objects.create(title="Campagne Arrêtée", message=f"{campaign.name} a été forcée à l'arrêt.", type="ERROR")
            
            # Ordre C2 : Demande à l'agent de supprimer physiquement les fichiers !
            for agent in active_agents:
                AgentCommand.objects.create(agent=agent, command='CLEANUP_HONEYTOKENS')
            
        elif action == 'EXTEND':
            mins = int(data.get('minutes', 60))
            if campaign.status == 'Completed':
                elapsed_total_minutes = (timezone.now() - campaign.created_at).total_seconds() / 60.0
                campaign.duration_minutes = int(elapsed_total_minutes) - campaign.total_paused_minutes + mins
                campaign.status = 'Running'
            else:
                campaign.duration_minutes += mins
            campaign.save()

        elif action == 'DELETE':
            campaign.is_deleted = True
            campaign.save()
            SystemNotification.objects.create(title="Campagne Supprimée", message=f"{campaign.name} a été placée aux archives.", type="INFO")
            # Pour Delete, on envoie aussi le nettoyage par sécurité
            for agent in active_agents:
                AgentCommand.objects.create(agent=agent, command='CLEANUP_HONEYTOKENS')
            
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required(login_url='login')
def campaign_live_logs(request, campaign_id):
    """ API pour le flux de logs dynamique du dashboard """
    campaign = get_object_or_404(TestCampaign, id=campaign_id)
    
    # Récupérer les agents ciblés par la campagne
    if campaign.target_department == 'ALL':
        agents = Agent.objects.all()
    else:
        agents = Agent.objects.filter(employee__department=campaign.target_department)
        
    # Filtrage basique (On pourrait lier les logs à la campagne directement plus tard)
    logs = AgentLog.objects.filter(agent__in=agents).order_by('-timestamp')[:50]
    
    logs_data = [{
        'time': log.timestamp.strftime("%H:%M:%S"),
        'agent': log.agent.hostname,
        'level': log.level,
        'msg': log.message
    } for log in logs]
    
    return JsonResponse({'logs': logs_data})

@login_required(login_url='login')
def campaign_management(request):
    """ Page de liste et de statistiques de toutes les campagnes """
    campaigns = TestCampaign.objects.filter(is_deleted=False).order_by('-created_at')    
    # Statistiques globales
    stats = {
        'total': campaigns.count(),
        'running': campaigns.filter(status='Running').count(),
        'paused': campaigns.filter(status='Paused').count(),
        'completed': campaigns.filter(status='Completed').count(),
    }
    
    return render(request, 'behavioral/campaign_management.html', {
        'campaigns': campaigns,
        'stats': stats
    })

