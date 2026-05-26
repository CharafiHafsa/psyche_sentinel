import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Q
from core.models import Employee
from .models import Agent, DeploymentConsentLog, AgentCommand, AgentLog, TestCampaign, SimulationModule, HoneytokenTemplate, HoneytokenInstance, SystemNotification, AILeakAlert, AZKAuthRecord
from .models import generate_meaningful_name
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

def calculate_ai_risk(campaign, total_targets):
    """ Calcule le risque spécifique au module Shadow AI """
    alerts = AILeakAlert.objects.filter(campaign=campaign)
    
    if not alerts.exists() or total_targets == 0:
        return {'score': 0, 'label': 'LOW', 'exposure': 0, 'sensitivity': 0, 'repetition': 0, 'confidence': 0}

    # 1. Exposure (% d'employés touchés)
    affected_count = alerts.values('agent').distinct().count()
    exposure = (affected_count / total_targets) * 100

    # 2. Sensitivity (Moyenne de la gravité, ramenée sur 100)
    avg_severity = alerts.aggregate(Avg('severity'))['severity__avg'] or 0
    sensitivity = (avg_severity / 5.0) * 100

    # 3. Repetition (% d'utilisateurs ayant fuité 3 fois ou plus)
    repeated_users = alerts.values('agent').annotate(c=Count('id')).filter(c__gte=3).count()
    repetition = (repeated_users / total_targets) * 100

    # 4. Confidence (Moyenne de la confiance de détection)
    avg_confidence = alerts.aggregate(Avg('confidence'))['confidence__avg'] or 0
    confidence_score = (avg_confidence / 5.0) * 100

    # FORMULE DU RISQUE IA
    score = (0.35 * exposure) + (0.30 * sensitivity) + (0.20 * repetition) + (0.15 * confidence_score)
    score = min(max(score, 0), 100)

    # Classification
    label = "LOW"
    color = "var(--color-success)"
    if score >= 75: 
        label = "CRITICAL"
        color = "var(--color-danger)"
    elif score >= 50: 
        label = "HIGH"
        color = "var(--color-warning)"
    elif score >= 25: 
        label = "MEDIUM"
        color = "var(--color-info)"

    return {
        'score': int(score),
        'label': label,
        'color': color,
        'exposure': int(exposure),
        'sensitivity': int(sensitivity),
        'repetition': int(repetition),
        'confidence': int(confidence_score)
    }

def calculate_azk_risk(campaign, total_targets):
    """ Calcule le risque organisationnel lié aux mots de passe (Zero-Knowledge) """
    records = AZKAuthRecord.objects.filter(campaign=campaign)
    
    if not records.exists() or total_targets == 0:
        return {'score': 0, 'label': 'LOW', 'color': 'var(--color-success)', 
                'exposure': 0, 'breach_risk': 0, 'compliance': 0, 'criticality': 0}

    # 1. Exposure (% d'employés avec un score <= 4, c'est-à-dire WEAK ou CRITICAL)
    weak_users = records.filter(score__lte=4).values('agent').distinct().count()
    exposure = (weak_users / total_targets) * 100

    # 2. Breach Risk (% d'employés utilisant un mot de passe compromis)
    breached_users = records.filter(is_breached=True).values('agent').distinct().count()
    breach_risk = (breached_users / total_targets) * 100

    # 3. Compliance (% d'employés violant la politique de sécurité)
    non_compliant_users = records.filter(is_policy_compliant=False).values('agent').distinct().count()
    compliance_risk = (non_compliant_users / total_targets) * 100

    # 4. Criticality (Sévérité moyenne des faiblesses)
    total_criticality = 0
    for r in records:
        if r.score <= 2: total_criticality += 100   # CRITICAL
        elif r.score <= 4: total_criticality += 70  # WEAK
        elif r.score <= 6: total_criticality += 40  # MEDIUM
        else: total_criticality += 10               # STRONG
        
    criticality = total_criticality / records.count()

    # FORMULE DU RISQUE AZK (Le vôtre, parfaitement équilibré)
    score = (0.35 * exposure) + (0.35 * breach_risk) + (0.20 * compliance_risk) + (0.10 * criticality)
    score = min(max(score, 0), 100)

    # Classification
    label = "LOW"
    color = "var(--color-success)"
    if score >= 75: 
        label = "CRITICAL"
        color = "var(--color-danger)"
    elif score >= 50: 
        label = "HIGH"
        color = "var(--color-warning)"
    elif score >= 25: 
        label = "MEDIUM"
        color = "var(--color-info)"

    return {
        'score': int(score),
        'label': label,
        'color': color,
        'exposure': int(exposure),
        'breach_risk': int(breach_risk),
        'compliance': int(compliance_risk),
        'criticality': int(criticality)
    }

def calculate_global_risk(module_codes, honeytoken_risk, ai_risk, auth_risk):
    """ Calcule le risque global normalisé basé uniquement sur les modules actifs """
    
    # Les poids "idéaux" (L'architecture que vous avez définie)
    base_weights = {
        'HONEYTOKEN': 0.35,
        'AI_LEAK': 0.35,
        'PHISHING': 0.20,
        'AUTH': 0.10  # Notre nouveau module !
    }

    active_weights = {code: base_weights[code] for code in module_codes if code in base_weights}
    total_active_weight = sum(active_weights.values())

    if total_active_weight == 0:
        return {'score': 0, 'label': 'LOW', 'color': 'var(--color-success)', 'weights': {}}

    normalized_weights = {code: (weight / total_active_weight) for code, weight in active_weights.items()}

    # Calcul dynamique de la note globale
    global_score = 0
    if 'HONEYTOKEN' in normalized_weights:
        global_score += honeytoken_risk.get('score', 0) * normalized_weights['HONEYTOKEN']
    if 'AI_LEAK' in normalized_weights:
        global_score += ai_risk.get('score', 0) * normalized_weights['AI_LEAK']
    if 'AUTH' in normalized_weights:
        global_score += auth_risk.get('score', 0) * normalized_weights['AUTH'] # NOUVEAU
        
    global_score = int(global_score)
    
    # Classification Globale
    label = "LOW"
    color = "var(--color-success)"
    if global_score >= 75: 
        label = "CRITICAL"
        color = "var(--color-danger)"
    elif global_score >= 50: 
        label = "HIGH"
        color = "var(--color-warning)"
    elif global_score >= 25: 
        label = "MEDIUM"
        color = "var(--color-info)"

    dashoffset = 414 - (4.14 * global_score)

    return {
        'score': global_score,
        'label': label,
        'color': color,
        'weights': normalized_weights,
        'dashoffset': dashoffset
    }

def calculate_single_agent_risk(agent, campaign, module_codes):
    """ Calcule le risque détaillé d'un employé avec explicabilité (Explainability) """
    risk_data = {
        'global_score': 0, 'global_label': 'LOW', 'color': 'var(--color-success)',
        'honeytoken': None, 'ai_leak': None, 'azk': None,
        'explanations': [] # NOUVEAU : Raisons comportementales
    }
    
    base_weights = {
    'HONEYTOKEN': 0.40,
    'AI_LEAK': 0.40,
    'AUTH': 0.20
}
    active_weights = {k: v for k, v in base_weights.items() if k in module_codes}
    total_weight = sum(active_weights.values())
    
    if total_weight == 0: return risk_data
    norm_weights = {k: v / total_weight for k, v in active_weights.items()}
    global_score = 0
    explanations = []
    
    # --- 1. HONEYTOKEN MODULE ---
    if 'HONEYTOKEN' in module_codes:
        h_instances = HoneytokenInstance.objects.filter(agent=agent, campaign=campaign, triggered=True)
        if h_instances.exists():
            count = h_instances.count()
            # Correction : Utilisation de la moyenne (Average) au lieu du Max
            avg_sev = sum([h.highest_severity for h in h_instances]) / count
            severity_score = (avg_sev / 10.0) * 100
            
            escalation = 30
            for h in h_instances:
                seq = [item.get('action') if isinstance(item, dict) else item for item in h.action_sequence]
                if 'DELETE' in seq: escalation = max(escalation, 100)
                elif 'MODIFY' in seq: escalation = max(escalation, 70)
            
            if count == 1:
                recurrence = 20
            elif count == 2:
                recurrence = 40
            elif count == 3:
                recurrence = 60
            elif count <= 5:
                recurrence = 80
            else:
                recurrence = 100
            
            min_time = min([h.time_to_trigger_seconds for h in h_instances if h.time_to_trigger_seconds is not None] or [99999])
            # Correction : Renommé Intent en Urgency (Curiosité)
            if min_time < 30:
                urgency = 100
            elif min_time < 300:
                urgency = 80
            elif min_time < 3600:
                urgency = 60
            elif min_time < 86400:
                urgency = 40
            else:
                urgency = 20
            
            h_score = (0.40 * severity_score) + (0.25 * escalation) + (0.20 * recurrence) + (0.15 * urgency)
            risk_data['honeytoken'] = {
                'score': int(h_score),
                'metrics': {'severity': int(severity_score), 'escalation': escalation, 'recurrence': recurrence, 'urgency': urgency} # 'urgency' remplace 'intent'
            }
            global_score += h_score * norm_weights['HONEYTOKEN']
            
            # EXPLICABILITÉ
            explanations.append(f"Curiosité anormale : A interagi avec {count} leurre(s).")
            if escalation == 100: explanations.append("Comportement agressif : Tentative de dissimulation (Suppression du fichier).")
            elif escalation == 70: explanations.append("Manipulation : Tentative de modification d'un fichier sensible.")
            if urgency == 100: explanations.append("Forte réactivité (< 30s) : Indique une surveillance active des cibles.")
        else:
            risk_data['honeytoken'] = {'score': 0, 'metrics': {}}

    # --- 2. SHADOW AI MODULE ---
    if 'AI_LEAK' in module_codes:
        alerts = AILeakAlert.objects.filter(agent=agent, campaign=campaign)
        if alerts.exists():
            count = alerts.count()
            avg_sev = sum([a.severity for a in alerts]) / count
            sensitivity = (avg_sev / 5.0) * 100
            repetition = min(count * 12, 100)
            avg_conf = sum([a.confidence for a in alerts]) / count
            confidence = (avg_conf / 5.0) * 100
            
            max_vol = max([a.clipboard_length for a in alerts])
            if max_vol > 3000: volume = 100
            elif max_vol > 1000: volume = 70
            else: volume = 30
            
            ai_score = (0.35 * sensitivity) + (0.25 * repetition) + (0.25 * confidence) + (0.15 * volume)
            risk_data['ai_leak'] = {
                'score': int(ai_score),
                'metrics': {'sensitivity': int(sensitivity), 'repetition': repetition, 'confidence': int(confidence), 'volume': volume}
            }
            global_score += ai_score * norm_weights['AI_LEAK']
            
            # EXPLICABILITÉ
            platforms = list(set(a.ai_platform for a in alerts))
            types = list(set(a.data_type_detected for a in alerts))

            explanations.append(
                f"DLP : {count} fuite(s) détectée(s) vers {', '.join(platforms)}."
            )

            explanations.append(
                f"Types de données exposés : {', '.join(types)}."
            )
            if avg_sev >= 4: explanations.append("Risque de fuite critique (clés API, credentials ou code source détectés).")
            if max_vol > 1000: explanations.append("Fuite massive : Grand volume de données copié.")
        else:
            risk_data['ai_leak'] = {'score': 0, 'metrics': {}}

    # --- 3. AZK AUTH MODULE ---
    if 'AUTH' in module_codes:
        record = AZKAuthRecord.objects.filter(agent=agent, campaign=campaign).order_by('-timestamp').first()
        if record:
            weakness = (10 - record.score) * 10
            breach = 100 if record.is_breached else 0
            compliance = 0 if record.is_policy_compliant else 100
            
            azk_score = (0.40 * weakness) + (0.35 * breach) + (0.25 * compliance)
            risk_data['azk'] = {
                'score': int(azk_score),
                'metrics': {'weakness': int(weakness), 'breach': breach, 'compliance': compliance}
            }
            global_score += azk_score * norm_weights['AUTH']
            
            # EXPLICABILITÉ
            if record.is_breached: explanations.append("Vulnérabilité Auth : Le mot de passe utilisé a fuité sur HaveIBeenPwned.")
            if not record.is_policy_compliant: explanations.append("Politique RH : Le mot de passe enfreint la politique de complexité de l'entreprise.")

        else:
            risk_data['azk'] = {'score': 0, 'metrics': {}}
            
    # --- 4. GLOBAL ---
    if not explanations:
        explanations.append("Aucun comportement à risque détecté durant cette campagne.")
    global_score = min(max(int(global_score), 0), 100)
    risk_data['global_score'] = global_score
    risk_data['explanations'] = explanations # Sauvegarde pour le ML et UI
    
    if global_score >= 75: risk_data['global_label'], risk_data['color'] = 'CRITICAL', 'var(--color-danger)'
    elif global_score >= 50: risk_data['global_label'], risk_data['color'] = 'HIGH', 'var(--color-warning)'
    elif global_score >= 25: risk_data['global_label'], risk_data['color'] = 'MEDIUM', '#eab308'
    
    return risk_data

def cleanup_pending_commands(campaign):
    """ 
    Supprime toutes les commandes non exécutées d'une campagne définitivement arrêtée 
    et génère un log pour prévenir l'administrateur.
    """
    pending_cmds = AgentCommand.objects.filter(campaign=campaign, is_executed=False)
    
    if not pending_cmds.exists():
        return # Rien à nettoyer

    # On regroupe par agent pour faire un log précis par machine
    agents_affected = pending_cmds.values_list('agent', flat=True).distinct()
    
    for agent_id in agents_affected:
        # On compte combien de commandes on va supprimer pour cet agent
        count = pending_cmds.filter(agent_id=agent_id).count()
        agent = Agent.objects.get(id=agent_id)
        
        # On crée le log d'avertissement
        AgentLog.objects.create(
            agent=agent,
            campaign=campaign,
            level='WARNING',
            message=f"🛑 Fin de campagne : {count} ordre(s) non exécuté(s) supprimé(s) de la file d'attente."
        )
        
    # Destruction finale des commandes dans la base de données
    pending_cmds.delete()

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
        send_behavioral_notification(
    request, 
    title="Agent Furtif Généré", 
    msg=f"Le jeton d'installation a été créé pour l'employé {employee.full_name}.", 
    notif_type="SUCCESS"
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
        if agent.status in ['Offline', 'Pending']:
            agent.status = 'Online'
        agent.save()

        now = timezone.now()
        
        # 1. On fige la liste exacte des commandes valides à la seconde T
        pending_cmds = list(AgentCommand.objects.filter(
            agent=agent, 
            is_executed=False, 
            execute_at__lte=now,
            campaign__status='Running'
        ))
        
        command_list = []
        cmd_ids_to_update = [] # On stocke les IDs pour les mettre à jour de façon sécurisée
        
        for cmd in pending_cmds:
            command_list.append({
                'command': cmd.command,
                'payload': cmd.payload
            })
            cmd_ids_to_update.append(cmd.id)
        
        # 2. On met à jour UNIQUEMENT ces IDs précis (évite d'écraser des commandes arrivées entre temps)
        if cmd_ids_to_update:
            AgentCommand.objects.filter(id__in=cmd_ids_to_update).update(is_executed=True)

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
        
        # --- NOUVEAU : Récupération du Tag de Campagne ---
        campaign_id = data.get('campaign_id')
        campaign_obj = None
        
        if campaign_id:
            # On cherche la campagne. On utilise filter().first() pour ne pas 
            # faire crasher le serveur si l'ID est introuvable.
            campaign_obj = TestCampaign.objects.filter(id=campaign_id).first()

        # Enregistrement du log avec son lien de campagne
        AgentLog.objects.create(
            agent=agent,
            campaign=campaign_obj, # <-- NOUVEAU LIEN DB (Peut être None pour les logs système)
            level=data.get('level', 'INFO'),
            message=data.get('message')
        )
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        # Il est toujours bon de renvoyer l'erreur exacte en mode dev pour le debug
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

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
                if t_hours <= 1.0:
                    max_jitter_hours = 2.0 / 60.0  # 2 minutes max pour les tests courts
                else:
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
                    "campaign_id": campaign.id,
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
                    campaign=campaign,
                    command='DEPLOY_HONEYTOKEN',
                    payload=payload,
                    execute_at=execution_time 
                )


def _deploy_ai_leak_module(campaign, active_agents):
    """ Ordonne aux agents de démarrer le keylogger éthique """
    for agent in active_agents:
        AgentCommand.objects.create(
            agent=agent,
            campaign=campaign,
            command='START_AI_MONITOR',
            payload={'campaign_id': campaign.id}
        )

def _deploy_auth_module(campaign , active_agents):
    """ Envoie l'ordre AZK à tous les agents ciblés """
    for agent in active_agents:
        AgentCommand.objects.create(
            agent=agent,
            campaign=campaign,
            command='START_ZAK_CHECK',
            payload={'campaign_id': campaign.id}
        )
@csrf_exempt
@require_POST
def honeytoken_deployed_ack(request):
    """ Reçoit la confirmation de l'agent avec le chemin absolu généré """
    try:
        data = json.loads(request.body)
        agent = Agent.objects.get(token=data.get('token'))
        instance = HoneytokenInstance.objects.get(id=data.get('instance_id'), agent=agent)
        
        # On met à jour le chemin réel pour retirer "En attente..."
        instance.file_path = data.get('file_path')
        instance.save()
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    
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
            modules = SimulationModule.objects.filter(id__in=module_ids)
            campaign_name = generate_meaningful_name(modules, target_dept)
            campaign = TestCampaign.objects.create(
                name=campaign_name,
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
                    _deploy_ai_leak_module(campaign, active_agents)
                elif module.code == 'AUTH':            
                    _deploy_auth_module(campaign, active_agents) 

            send_behavioral_notification(
                request, 
                title="Campagne Lancée", 
                msg=f"L'opération a été déployée avec succès sur le département {campaign.target_department}.", 
                notif_type="SUCCESS",
                link=f"/behavioral/campaign/{campaign.id}/"
            )

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
        
        # On vérifie la dernière action pour éviter les doublons frénétiques de l'OS
        last_action = sequence[-1].get('action') if sequence and isinstance(sequence[-1], dict) else (sequence[-1] if sequence else None)
        
        if not sequence or last_action != action:
            # On stocke maintenant un dictionnaire avec l'heure exacte formatée
            time_str = now.strftime("%d/%m/%Y %H:%M:%S")
            sequence.append({"action": action, "time": time_str})
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
        campaign_id = data.get('campaign_id')
        
        ai_platform = data.get('ai_platform', 'Inconnu')
        data_type = data.get('data_type', 'UNKNOWN')
        length = data.get('length', 0)
        severity = data.get('severity', 1)
        action = data.get('action', 'PASTE')
        confidence = data.get('confidence', 4)
        reasons = data.get('reasons', [])

        agent = Agent.objects.get(token=token)
        
        # On trouve la campagne AI_LEAK actuellement en cours
        campaign = get_object_or_404(TestCampaign, id=campaign_id)
        
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
            severity=severity,
            confidence=confidence,
            reasons=reasons
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

import random
from django.utils import timezone
from datetime import timedelta

@csrf_exempt
@require_POST
def azk_trigger(request):
    try:
        data = json.loads(request.body)
        token = data.get('token')
        campaign_id = data.get('campaign_id')
        status = data.get('status', 'COMPLETED')
        metadata = data.get('metadata', {})

        agent = Agent.objects.get(token=token)
        campaign = get_object_or_404(TestCampaign, id=campaign_id)
        
        if not campaign:
            return JsonResponse({'success': False, 'error': 'Aucune campagne AUTH active.'})

        if status == "COMPLETED":
            # 1. SUCCÈS : Enregistrement des données AZK
            AZKAuthRecord.objects.create(
                agent=agent, campaign=campaign,
                length=metadata.get('length', 0),
                entropy=metadata.get('entropy', 0),
                is_breached=metadata.get('breached', False),
                has_common_pattern=metadata.get('common', False),
                score=metadata.get('score', 0),
                is_policy_compliant=metadata.get('policy_compliant', False)
            )
            AgentLog.objects.create(agent=agent, level='INFO', message=f"🔐 AZK : Audit réussi. L'employé a participé.")
            
            # Vérification de l'Auto-Complétion de la campagne
            check_campaign_auto_completion(campaign)
            
        else:
            # 2. ÉCHEC / ANNULATION / BUSY : Gestion des Retries
            
            # On compte combien de fois on a déjà essayé d'envoyer la commande AZK à cet agent
            attempts = AgentCommand.objects.filter(agent=agent, command='START_ZAK_CHECK', campaign=campaign).count()
            
            if attempts >= 3:
                # Limite atteinte
                final_status = "CANCELLED_MAX" if status == "CANCELLED" else "NO_RESPONSE_MAX"
                AgentLog.objects.create(agent=agent, level='WARNING', message=f"🔐 AZK : Limite de réessais atteinte ({final_status}). Test abandonné pour cet agent.")
                check_campaign_auto_completion(campaign)
            else:
                # --- 1. CALCUL DU TEMPS RESTANT DE LA CAMPAGNE ---
                elapsed_minutes = (timezone.now() - campaign.created_at).total_seconds() / 60.0
                remaining_minutes = (campaign.duration_minutes + campaign.total_paused_minutes) - elapsed_minutes
                
                # Si la campagne est sur le point de se terminer (moins de 1 minute), on abandonne le réessai
                if remaining_minutes <= 1:
                    AgentLog.objects.create(agent=agent, level='WARNING', message="🔐 AZK : Fin de campagne imminente, test abandonné pour cet agent.")
                    check_campaign_auto_completion(campaign)
                    return JsonResponse({'success': True})

                # --- 2. PLANIFICATION DE BASE ---
                base_delay = 45
                offset = random.randint(-15, 15)
                retry_minutes = base_delay + offset
                
                # --- 3. ADAPTATION DYNAMIQUE ---
                # Si le retry calculé dépasse le temps restant de la campagne, on le raccourcit !
                if retry_minutes >= remaining_minutes:
                    if remaining_minutes > 5:
                        # S'il reste par ex 15 min, on tape au hasard entre 2 et 14 minutes
                        retry_minutes = random.randint(2, int(remaining_minutes - 1))
                    else:
                        # S'il reste moins de 5 min, on relance dans 1 minute chrono
                        retry_minutes = 1
                
                next_execution = timezone.now() + timedelta(minutes=retry_minutes)
                
                AgentCommand.objects.create(
                    agent=agent,
                    campaign=campaign,
                    command='START_ZAK_CHECK',
                    execute_at=next_execution,
                    payload={'campaign_id': campaign.id}
                )
                
                reason_map = {
                    "CANCELLED": "Fenêtre fermée par l'employé",
                    "NO_RESPONSE": "Aucune interaction (Timeout)",
                    "BUSY": "Employé absent ou en mode présentation"
                }
                
                AgentLog.objects.create(
                    agent=agent, level='WARNING', 
                    message=f"🔐 AZK : {reason_map.get(status, status)}. Réessai planifié dynamiquement dans {retry_minutes} minute(s)."
                )

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

def check_campaign_auto_completion(campaign):
    """ Ferme automatiquement la campagne si AZK est le seul module et que tous les agents ont fini """
    
    # Si la campagne a d'autres modules (IA, Honeytoken), on ne l'auto-complète pas
    if campaign.modules.count() > 1:
        return
        
    active_agents = Agent.objects.filter(
        employee__department=campaign.target_department
    ).exclude(status='Pending') if campaign.target_department != 'ALL' else Agent.objects.exclude(status='Pending')
    
    total_active = active_agents.count()
    if total_active == 0: return

    # Combien d'agents ont un enregistrement AZK (COMPLETED) ?
    completed_count = AZKAuthRecord.objects.filter(campaign=campaign).values('agent').distinct().count()
    
    # Combien d'agents ont atteint la limite de Retry (3 commandes envoyées et toujours pas de record) ?
    # On cherche les agents qui ont 3 commandes START_ZAK_CHECK mais aucun AZKAuthRecord
    maxed_out_count = 0
    for agent in active_agents:
        if not AZKAuthRecord.objects.filter(campaign=campaign, agent=agent).exists():
            cmds = AgentCommand.objects.filter(agent=agent, command='START_ZAK_CHECK').count()
            if cmds >= 3:
                maxed_out_count += 1
                
    # Si la somme des agents ayant réussi + les agents ayant échoué 3 fois = le total des agents
    if (completed_count + maxed_out_count) >= total_active:
        campaign.status = 'Completed'
        campaign.save()
        cleanup_pending_commands(campaign)
        
@login_required(login_url='login')
def campaign_dashboard(request, campaign_id):
    # On bloque l'accès si la campagne est supprimée
    campaign = get_object_or_404(TestCampaign, id=campaign_id, is_deleted=False)
    campaign_logs = AgentLog.objects.filter(campaign=campaign).order_by('-timestamp')[:50]
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
        cleanup_pending_commands(campaign)

    total_seconds = (campaign.duration_minutes + campaign.total_paused_minutes) * 60
    elapsed_seconds = (timezone.now() - campaign.created_at).total_seconds()
    if campaign.status == 'Paused' and campaign.last_paused_at:
         elapsed_seconds -= (timezone.now() - campaign.last_paused_at).total_seconds()

    progress_percent = min(100, int((elapsed_seconds / total_seconds) * 100)) if not is_expired else 100

    # --- 3. DÉTAILS ET ANALYSE HONEYTOKEN ---
    honeytoken_stats = {}
    instances = []
    
    # Variables comportementales Honeytoken
    action_counts = {'OPEN': 0, 'MODIFY': 0, 'DELETE': 0}
    destructive_count = 0
    dept_triggers = {}

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

    # --- 5. MOTEUR DE RISQUE GLOBAL ET SOUS-RISQUES ---
    # Valeurs par défaut sécurisées
    honeytoken_risk = {'score': 0, 'label': 'LOW', 'color': 'var(--color-success)', 'exposure': 0, 'behavior': 0, 'impact': 0}
    ai_risk = {'score': 0, 'label': 'LOW', 'color': 'var(--color-success)', 'exposure': 0, 'sensitivity': 0, 'repetition': 0, 'confidence': 0}
    auth_risk = {'score': 0, 'label': 'LOW', 'color': 'var(--color-success)', 'exposure': 0, 'breach_risk': 0, 'compliance': 0, 'criticality': 0}

    azk_records = []
    azk_stats = {}

    # --- NOUVEAU : Récupération des données AZK ---
    if 'AUTH' in module_codes:
        azk_records = AZKAuthRecord.objects.filter(campaign=campaign).order_by('-timestamp')
        if azk_records.exists():
            avg_entropy = azk_records.aggregate(Avg('entropy'))['entropy__avg'] or 0
            
            azk_stats = {
                'total_audits': azk_records.count(),
                'avg_entropy': int(avg_entropy),
                'breached_count': azk_records.filter(is_breached=True).count(),
                'compliant_count': azk_records.filter(is_policy_compliant=True).count()
            }

    # Calcul dynamique basé sur les agents actifs
    if active_count > 0:
        if 'HONEYTOKEN' in module_codes:
            honeytoken_risk = calculate_honeytoken_risk(campaign, active_count)
            
        if 'AI_LEAK' in module_codes:
            ai_risk = calculate_ai_risk(campaign, active_count)
            
        if 'AUTH' in module_codes:
            auth_risk = calculate_azk_risk(campaign, active_count)

    # N'OUBLIEZ PAS D'AJOUTER auth_risk DANS L'APPEL ICI :
    global_risk = calculate_global_risk(module_codes, honeytoken_risk, ai_risk, auth_risk)

    campaign.global_risk_score = global_risk.get('score')
    campaign.global_risk_label = global_risk.get('label')
    campaign.risk_calculated_at = timezone.now()

    # On n'enregistre le score que si le module est actif. 
    # Sinon, on le force à None (NULL) pour ne pas fausser le Machine Learning.
    if 'HONEYTOKEN' in module_codes:
        campaign.honeytoken_risk_score = honeytoken_risk.get('score')
    else:
        campaign.honeytoken_risk_score = None

    if 'AI_LEAK' in module_codes:
        campaign.ai_risk_score = ai_risk.get('score')
    else:
        campaign.ai_risk_score = None

    if 'AUTH' in module_codes:
        campaign.azk_risk_score = auth_risk.get('score')
    else:
        campaign.azk_risk_score = None

    campaign.save(update_fields=[
        'global_risk_score', 'global_risk_label', 'risk_calculated_at',
        'honeytoken_risk_score', 'ai_risk_score', 'azk_risk_score'
    ])

    # --- 6. ÉVALUATION DE LA FIABILITÉ DE LA COUVERTURE ---
    reliability_level = "HIGH"
    reliability_color = "var(--color-success)"
    if coverage_percent < 40:
        reliability_level = "LOW"
        reliability_color = "var(--color-danger)"
    elif coverage_percent < 70:
        reliability_level = "MEDIUM"
        reliability_color = "var(--color-warning)"

    missing_employees_list = list(no_agent_employees) + [a.employee for a in pending_agents]

    # === NOUVEAU : CALCUL DES RISQUES INDIVIDUELS ===
    agents_risk_data = {}
    for agent in active_agents:
        # Calcul du risque
        risk_details = calculate_single_agent_risk(agent, campaign, module_codes)
        
        # Récupération des logs spécifiques
        agent_logs = AgentLog.objects.filter(agent=agent, campaign=campaign).order_by('-timestamp')[:50]
        logs_list = [{
            'timestamp': log.timestamp.strftime("%d/%m %H:%M:%S"),
            'level': log.level,
            'message': log.message
        } for log in agent_logs]
        
        # Ajout au dictionnaire JSON
        agents_risk_data[str(agent.id)] = {
            'name': agent.employee.full_name,
            'hostname': agent.hostname or "Inconnu",
            'department': agent.employee.department or "-",
            'is_online': agent.is_online_realtime,
            'status': agent.status,
            'risk': risk_details,
            'logs': logs_list
        }
        
        # Attachement direct à l'objet pour l'affichage dans le tableau HTML
        agent.computed_risk = risk_details

    # Convertir en JSON pour le Frontend
    agents_risk_json = json.dumps(agents_risk_data)

    # --- 7. CONSTRUCTION DU CONTEXTE ---
    context = {
        'campaign': campaign,
        'logs': campaign_logs,
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
        
        'missing_employees': missing_employees_list,

        # NOUVEAU : Le triptyque du risque
        'global_risk': global_risk,
        'honeytoken_risk': honeytoken_risk,
        'ai_risk': ai_risk,
        
        'reliability_level': reliability_level,
        'reliability_color': reliability_color,
        
        # Données Honeytoken (Analyse)
        'honeytoken_stats': honeytoken_stats,
        'instances': instances,
        'action_counts': action_counts,
        'destructive_count': destructive_count,
        'dept_triggers': dept_triggers,

        # Données Shadow AI
        'ai_alerts': ai_alerts,
        'ai_stats': ai_stats,

        # NOUVEAU : Données AZK
        'auth_risk': auth_risk,
        'azk_records': azk_records,
        'azk_stats': azk_stats,

        'agents_risk_json': agents_risk_json,
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

        # NOUVEAU : On vérifie si le module HONEYTOKEN fait partie de cette campagne
        has_honeytoken = campaign.modules.filter(code='HONEYTOKEN').exists()

        # 2. Traitement des actions
        if action == 'PAUSE' and campaign.status == 'Running':
            campaign.status = 'Paused'
            campaign.last_paused_at = timezone.now()
            campaign.save()
            SystemNotification.objects.create(title="Campagne en Pause", message=f"{campaign.name} a été suspendue.", type="WARNING")
            
            # Ordre C2 (Avec isolation de campagne)
            for agent in active_agents:
                AgentCommand.objects.create(
                    agent=agent, 
                    campaign=campaign,
                    command='PAUSE_CAMPAIGN',
                    payload={'campaign_id': campaign.id}
                )
            
        elif action == 'RESUME' and campaign.status == 'Paused':
            campaign.status = 'Running'
            pause_dur = (timezone.now() - campaign.last_paused_at).total_seconds() / 60.0
            campaign.total_paused_minutes += int(pause_dur)
            campaign.last_paused_at = None
            campaign.save()
            
            # Ordre C2 (Avec isolation de campagne)
            for agent in active_agents:
                AgentCommand.objects.create(
                    agent=agent, 
                    campaign=campaign,
                    command='RESUME_CAMPAIGN',
                    payload={'campaign_id': campaign.id}
                )
            
        elif action == 'STOP':
            campaign.status = 'Completed'
            campaign.save()
            SystemNotification.objects.create(title="Campagne Arrêtée", message=f"{campaign.name} a été forcée à l'arrêt.", type="ERROR")
            
            # NOUVEAU : Nettoyage des commandes en attente (Garbage Collector)
            cleanup_pending_commands(campaign)
            
            # Ordre C2 : UNIQUEMENT SI LE MODULE HONEYTOKEN EST ACTIF
            if has_honeytoken:
                for agent in active_agents:
                    AgentCommand.objects.create(
                        agent=agent, 
                        campaign=campaign,
                        command='CLEANUP_HONEYTOKENS',
                        payload={'campaign_id': campaign.id}
                    )
            
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
            
            # NOUVEAU : Nettoyage des commandes en attente
            cleanup_pending_commands(campaign)
            
            # Ordre C2 : UNIQUEMENT SI LE MODULE HONEYTOKEN EST ACTIF
            if has_honeytoken:
                for agent in active_agents:
                    AgentCommand.objects.create(
                        agent=agent, 
                        campaign=campaign,
                        command='CLEANUP_HONEYTOKENS',
                        payload={'campaign_id': campaign.id}
                    )
            
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

def send_behavioral_notification(request, title, msg, notif_type='INFO', link=None):
    """
    1. Sauvegarde la notification en DB pour l'historique
    2. Nettoie les vieilles notifications expirées
    3. Envoie un Toast éphémère à l'UI avec le tag 'behavioral_app'
    """
    # Auto-nettoyage silencieux des notifications périmées
    SystemNotification.objects.filter(expires_at__lt=timezone.now()).delete()

    # 1. Enregistrement en base de données
    SystemNotification.objects.create(
        title=title,
        message=msg,
        type=notif_type,
        link=link
    )

    # 2. Envoi du Toast Django avec le tag spécifique
    level_map = {
        'INFO': messages.INFO,
        'SUCCESS': messages.SUCCESS,
        'WARNING': messages.WARNING,
        'ERROR': messages.ERROR
    }
    django_level = level_map.get(notif_type, messages.INFO)
    
    # On ajoute le tag "behavioral_app" pour isoler vos messages de ceux des autres
    messages.add_message(request, django_level, f"{title}|{msg}", extra_tags=f'behavioral_app {notif_type.lower()}')


def agent_details(request, agent_id):
    agent = get_object_or_404(Agent, id=agent_id)
    
    # 1. Tous les logs pour le terminal
    logs = AgentLog.objects.filter(agent=agent).order_by('-timestamp')
    
    # 2. Consentement
    consent_log = DeploymentConsentLog.objects.filter(agent_token=agent.token).first()
    
    # 3. Récupérer les campagnes où l'agent a eu des interactions
    campaign_ids = set()
    campaign_ids.update(AILeakAlert.objects.filter(agent=agent).values_list('campaign_id', flat=True))
    campaign_ids.update(HoneytokenInstance.objects.filter(agent=agent).values_list('campaign_id', flat=True))
    campaign_ids.update(AZKAuthRecord.objects.filter(agent=agent).values_list('campaign_id', flat=True))
    
    agent_campaigns = TestCampaign.objects.filter(id__in=campaign_ids).order_by('-created_at')

    # 4. Préparer les données détaillées par campagne
    campaign_results = []
    for camp in agent_campaigns:
        module_codes = [m.code for m in camp.modules.all()]
        
        # === APPEL DE LA NOUVELLE FONCTION ===
        agent_risk = calculate_single_agent_risk(agent, camp, module_codes)

        # Données AZK (Tous les audits de cette campagne)
        azk_records = AZKAuthRecord.objects.filter(agent=agent, campaign=camp).order_by('-timestamp')
        latest_azk = azk_records.first()
        
        # Données DLP (Toutes les fuites)
        leaks = AILeakAlert.objects.filter(agent=agent, campaign=camp).order_by('-timestamp')
        critical_leaks = leaks.filter(severity__gte=4).count()
        
        # Données Honeytokens (Tous les pièges déclenchés)
        honeytokens = HoneytokenInstance.objects.filter(agent=agent, campaign=camp, triggered=True).select_related('template').order_by('-triggered_at')
        max_honey = max([h.highest_severity for h in honeytokens]) if honeytokens else 0
        destructive_count = 0
        for h in honeytokens:
            if h.action_sequence and any(action in h.action_sequence for action in ['MODIFY', 'DELETE']):
                destructive_count += 1
        
        campaign_results.append({
            'campaign': camp,
            'risk': agent_risk,
            'azk_latest': latest_azk,
            'azk_records': azk_records,
            'leaks': leaks,
            'leaks_total': leaks.count(),
            'leaks_critical': critical_leaks,
            'honeytokens': honeytokens,
            'honey_triggered': honeytokens.count(),
            'honey_destructive': destructive_count,
            'max_honey': max_honey
        })

    context = {
        'agent': agent,
        'employee': agent.employee,
        'logs': logs,
        'consent_log': consent_log,
        'agent_campaigns': agent_campaigns,
        'campaign_results': campaign_results,
    }
    return render(request, 'behavioral/agent_details.html', context)