from asyncio import run
import random
from django.shortcuts import get_object_or_404, redirect, render
from .models import CampaignRun, CampaignScenario, Scenario, ScenarioResponse, CampaignEmployeeResult
from core.models import Employee
from datetime import datetime
from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from django.core.signing import Signer, BadSignature
from core.models import Employee
from django.utils.dateparse import parse_datetime
from django.core.mail import send_mail
from django.urls import reverse
import json
from .models import CampaignEmployeeTypeResult

def get_period_start(period):
    now = timezone.now()

    if period == 'today':
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == '7d':
        return now - timedelta(days=7)

    if period == '30d':
        return now - timedelta(days=30)

    if period == 'month':
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    return None

def send_campaign_reminders(campaign):

    pending_employees = get_pending_campaign_employees(
        campaign
    )

    for employee in pending_employees:

        campaign_link = (
            f"http://127.0.0.1:8000{campaign.start_link}"
        )

        send_mail(
            subject=f"Rappel - Campagne cybersécurité : {campaign.campaign_name}",

            message=(
                f"Bonjour {employee.full_name},\n\n"
                f"Ceci est un rappel pour compléter "
                f"la campagne de sensibilisation cybersécurité.\n\n"
                f"Lien : {campaign_link}\n\n"
                f"Merci de finaliser la campagne avant expiration."
            ),

            from_email='noreply@exemple.ma',

            recipient_list=[employee.email],

            fail_silently=False
        )
def calculate_score_from_counts(safe_count, warning_count, risk_count):
    total = safe_count + warning_count + risk_count

    if total == 0:
        return 0

    score = ((warning_count * 50) + (risk_count * 100)) / total

    return round(score)

def get_score_status(score):

    if score == 0:
        return "Aucun risque", "badge-success"

    if 1 <= score <= 33:
        return "Risque faible", "badge-info"

    if 34 <= score <= 66:
        return "Risque modéré", "badge-warning"

    if 67 <= score <= 99:
        return "Risque élevé", "badge-danger"

    return "Très risqué", "badge-danger"
# def get_score_status(score):
#     if score >= 71:
#         return "Risque élevé", "badge-danger"

#     if score >= 41:
#         return "Risque moyen", "badge-warning"

#     if score >= 21:
#         return "Vigilance", "badge-info"

#     return "Faible risque", "badge-success"

def update_campaign_employee_result(campaign_run, employee):
    responses = ScenarioResponse.objects.filter(
        campaign_run=campaign_run,
        employee=employee
    )

    safe_count = responses.filter(risk_result='safe').count()
    warning_count = responses.filter(risk_result='warning').count()
    risk_count = responses.filter(risk_result='risk').count()
    total_count = responses.count()

    score = calculate_score_from_counts(
        safe_count,
        warning_count,
        risk_count
    )

    status_label, badge_class = get_score_status(score)

    CampaignEmployeeResult.objects.update_or_create(
        campaign_run=campaign_run,
        employee=employee,
        defaults={
            'total_count': total_count,
            'safe_count': safe_count,
            'warning_count': warning_count,
            'risk_count': risk_count,
            'score': score,
            'status_label': status_label,
        }
    )

    scenario_types = [
        'phishing',
        'ai_leak',
        'document',
        'internal_chat',
        'sharing',
        'password',
    ]

    for scenario_type in scenario_types:
        type_responses = responses.filter(
            scenario__scenario_type=scenario_type
        )

        if not type_responses.exists():
            continue

        type_total = type_responses.count()
        type_safe = type_responses.filter(risk_result='safe').count()
        type_warning = type_responses.filter(risk_result='warning').count()
        type_risk = type_responses.filter(risk_result='risk').count()

        type_score = calculate_score_from_counts(
            type_safe,
            type_warning,
            type_risk
        )

        CampaignEmployeeTypeResult.objects.update_or_create(
            campaign_run=campaign_run,
            employee=employee,
            scenario_type=scenario_type,
            defaults={
                'total_count': type_total,
                'safe_count': type_safe,
                'warning_count': type_warning,
                'risk_count': type_risk,
                'score': type_score,
            }
        )

@login_required(login_url='login')
def attack_scenarios_dashboard(request):
    period = request.GET.get('period', '30d')
    selected_department = request.GET.get('department', 'all')
    period_start = get_period_start(period)

    departments = get_department_choices()

    campaigns = CampaignRun.objects.all().order_by('-created_at')

    if period_start:
        campaigns = campaigns.filter(created_at__gte=period_start)

    if selected_department != 'all':
        campaigns = [
            campaign for campaign in campaigns
            if (
                'all' in (campaign.target_departments or [])
                or selected_department in (campaign.target_departments or [])
            )
        ]

    campaign_rows = []

    all_responses = ScenarioResponse.objects.exclude(employee__isnull=True)
    if period_start:
        all_responses = all_responses.filter(created_at__gte=period_start)

    if selected_department != 'all':
        all_responses = all_responses.filter(employee__department=selected_department)

    total_campaigns = len(campaigns) if isinstance(campaigns, list) else campaigns.count()

    completed_participants = (
        all_responses
        .exclude(employee__isnull=True)
        .values('employee_id', 'campaign_run_id')
        .distinct()
        .count()
    )

    campaign_scores = []

    for campaign in campaigns:
        responses = ScenarioResponse.objects.filter(
            campaign_run=campaign
        ).exclude(employee__isnull=True)

        if selected_department != 'all':
            responses = responses.filter(employee__department=selected_department)

        if responses.exists():
            safe_count = responses.filter(risk_result='safe').count()
            warning_count = responses.filter(risk_result='warning').count()
            risk_count = responses.filter(risk_result='risk').count()

            campaign_scores.append(
                calculate_score_from_counts(
                    safe_count,
                    warning_count,
                    risk_count
                )
            )

    if campaign_scores:
        average_score = round(sum(campaign_scores) / len(campaign_scores))
    else:
        average_score = 0

    for campaign in campaigns:
        responses = ScenarioResponse.objects.filter(
            campaign_run=campaign
        ).exclude(employee__isnull=True)
        if selected_department != 'all':
            responses = responses.filter(employee__department=selected_department)

        participants = 0

        employee_scores = []

        employees = (
            responses
            .values_list('employee_id', flat=True)
            .distinct()
        )

        for employee_id in employees:

            employee_responses = responses.filter(employee_id=employee_id)

            employee_total = employee_responses.count()
            campaign_total = campaign.campaign_scenarios.count()

            if campaign_total == 0:
                campaign_total = campaign.question_count

            if employee_total < campaign_total:
                continue

            safe_count = employee_responses.filter(
                risk_result='safe'
            ).count()

            warning_count = employee_responses.filter(
                risk_result='warning'
            ).count()

            risk_count = employee_responses.filter(
                risk_result='risk'
            ).count()

            employee_score = calculate_score_from_counts(
                safe_count,
                warning_count,
                risk_count
            )

            participants += 1
            employee_scores.append(employee_score)

        if employee_scores:
            campaign_score = round(
                sum(employee_scores) / len(employee_scores)
            )
        else:
            campaign_score = 0
        campaign_departments = campaign.target_departments or ['all']

        if 'all' in campaign_departments:
            total_target_employees = Employee.objects.exclude(
                department__isnull=True
            ).exclude(
                department__exact=''
            ).count()
        else:
            total_target_employees = Employee.objects.filter(
                department__in=campaign_departments
            ).count()
        campaign_rows.append({
            'campaign': campaign,
            'participants': participants,
            'total_target_employees': total_target_employees,
            'score': campaign_score,
        })

    return render(request, 'announced_drills/attack_scenarios_dashboard.html', {
        'period': period,
        'selected_department': selected_department,
        'departments': departments,
        'total_campaigns': total_campaigns,
        'completed_participants': completed_participants,
        'average_score': average_score,
        'campaign_rows': campaign_rows,
    })
@login_required(login_url='login')
def global_statistics(request):
    period = request.GET.get('period', '30d')
    selected_department = request.GET.get('department', 'all')
    selected_campaign = request.GET.get('campaign', 'all')

    departments = get_department_choices()

    campaigns = CampaignRun.objects.all().order_by('-created_at')

    return render(request, 'announced_drills/global_statistics.html', {
        'period': period,
        'selected_department': selected_department,
        'selected_campaign': selected_campaign,
        'departments': departments,
        'campaigns': campaigns,
    })
@login_required(login_url='login')
def delete_campaign(request, run_id):
    campaign = get_object_or_404(CampaignRun, id=run_id)

    if request.method == 'POST':
        campaign.delete()

    return redirect('announced-attacks-dashboard')

def get_pending_campaign_employees(campaign):
    departments = campaign.target_departments or ['all']

    if 'all' in departments:
        target_employees = Employee.objects.exclude(
            email__isnull=True
        ).exclude(
            email__exact=''
        )
    else:
        target_employees = Employee.objects.filter(
            department__in=departments
        ).exclude(
            email__isnull=True
        ).exclude(
            email__exact=''
        )

    total_scenarios = campaign.campaign_scenarios.count()

    if total_scenarios == 0:
        total_scenarios = campaign.question_count

    completed_employee_ids = []

    for employee in target_employees:
        response_count = ScenarioResponse.objects.filter(
            campaign_run=campaign,
            employee=employee
        ).count()

        if response_count >= total_scenarios:
            completed_employee_ids.append(employee.id)

    return target_employees.exclude(id__in=completed_employee_ids)
@login_required(login_url='login')
def remind_campaign_pending_employees(request, run_id):
    campaign = get_object_or_404(CampaignRun, id=run_id)

    if campaign.expires_at and timezone.now() > campaign.expires_at:
        return redirect('announced-campaign-results', run_id=campaign.id)

    pending_employees = get_pending_campaign_employees(campaign)

    for employee in pending_employees:
        campaign_link = request.build_absolute_uri(campaign.start_link)

        send_mail(
            subject=f"Rappel - Campagne cybersécurité : {campaign.campaign_name}",
            message=(
                f"Bonjour {employee.full_name},\n\n"
                f"Ceci est un rappel pour compléter la campagne de sensibilisation cybersécurité.\n\n"
                f"Lien : {campaign_link}\n\n"
                f"Merci de finaliser la campagne avant expiration."
            ),
            from_email=None,
            recipient_list=[employee.email],
            fail_silently=False,
        )

    campaign.reminder_sent_at = timezone.now()
    campaign.save()

    return redirect('announced-campaign-results', run_id=campaign.id)

@login_required(login_url='login')
def campaign_results_detail(request, run_id):
    campaign = get_object_or_404(CampaignRun, id=run_id)

    responses = (
        ScenarioResponse.objects
        .filter(campaign_run=campaign)
        .exclude(employee__isnull=True)
    )

    employees = (
        responses
        .values_list('employee_id', flat=True)
        .distinct()
    )

    rows = []
    department_stats = {}
    sort_score = request.GET.get('sort_score', '')
    total_scenarios = campaign.campaign_scenarios.count()
    for employee_id in employees:
        employee = Employee.objects.get(id=employee_id)
        employee_responses = responses.filter(employee=employee)

        safe_count = employee_responses.filter(risk_result='safe').count()
        warning_count = employee_responses.filter(risk_result='warning').count()
        risk_count = employee_responses.filter(risk_result='risk').count()
        total = employee_responses.count()

        type_labels = {
            'phishing': 'Phishing email',
            'internal_chat': 'Simulation de messagerie interne',
            'ai_leak': 'Fuite de données via IA',
        }

        type_stats = []

        for scenario_type, label in type_labels.items():
            type_responses = employee_responses.filter(
                scenario__scenario_type=scenario_type
            )

            type_safe = type_responses.filter(risk_result='safe').count()
            type_warning = type_responses.filter(risk_result='warning').count()
            type_risk = type_responses.filter(risk_result='risk').count()
            type_total = type_responses.count()

            type_score = None

            if type_total > 0:
                type_score = calculate_score_from_counts(
                    type_safe,
                    type_warning,
                    type_risk
                )

            type_stats.append({
                'label': label,
                'safe': type_safe,
                'warning': type_warning,
                'risk': type_risk,
                'total': type_total,
                'score': type_score,
            })
        # score = calculate_score_from_counts(
        #     safe_count,
        #     warning_count,
        #     risk_count
        # )
        if total == 0:
            score = None
            status_label = "Non participé"
            badge_class = "badge-neutral"

        elif total < total_scenarios:
            score = None

            if campaign.status in ['expired', 'completed']:
                status_label = "Non complété"
                badge_class = "badge-warning"
            else:
                status_label = "En cours"
                badge_class = "badge-info"

        else:
            score = calculate_score_from_counts(
                safe_count,
                warning_count,
                risk_count
            )

            status_label, badge_class = get_score_status(score)

        # status_label, badge_class = get_score_status(score)

        rows.append({
            'employee': employee,
            'total': total,
            'safe_count': safe_count,
            'warning_count': warning_count,
            'risk_count': risk_count,
            'score': score,
            'status_label': status_label,
            'badge_class': badge_class,
            'has_participated': True,
            'type_stats': type_stats,
        })

        department = employee.department or "Non assigné"

        if department not in department_stats:
            department_stats[department] = {
                'department': department,
                'participants': set(),
                'employee_scores': [],
                'type_scores': {
                    'phishing': [],
                    'internal_chat': [],
                    'ai_leak': [],
                },
            }

        # department_stats[department]['participants'].add(employee.id)
        # department_stats[department]['employee_scores'].append(score)
        if total >= total_scenarios:
            department_stats[department]['participants'].add(employee.id)
            department_stats[department]['employee_scores'].append(score)
        for type_stat in type_stats:
            if type_stat['score'] is not None:
                if type_stat['label'] == 'Phishing email':
                    department_stats[department]['type_scores']['phishing'].append(type_stat['score'])

                elif type_stat['label'] == 'Simulation de messagerie interne':
                    department_stats[department]['type_scores']['internal_chat'].append(type_stat['score'])

                elif type_stat['label'] == 'Fuite de données via IA':
                    department_stats[department]['type_scores']['ai_leak'].append(type_stat['score'])
    campaign_departments = campaign.target_departments or ['all']

    if 'all' in campaign_departments:
            target_employees = Employee.objects.exclude(
                department__isnull=True
            ).exclude(
                department__exact=''
            )
    else:
            target_employees = Employee.objects.filter(
                department__in=campaign_departments
            )

    answered_employee_ids = set(employees)

    for employee in target_employees:
            if employee.id in answered_employee_ids:
                continue

            rows.append({
                'employee': employee,
                'total': 0,
                'safe_count': 0,
                'warning_count': 0,
                'risk_count': 0,
                'score': None,
                'status_label': 'Non participé',
                'badge_class': 'badge-neutral',
                'has_participated': False,
            })


    department_rows = []

    for dept_data in department_stats.values():
        if dept_data['employee_scores']:
            score = round(sum(dept_data['employee_scores']) / len(dept_data['employee_scores']))
        else:
            score = 0

        status_label, badge_class = get_score_status(score)

        total_department_employees = Employee.objects.filter(
            department=dept_data['department']
        ).count()
        type_labels = {
            'phishing': 'Phishing',
            'internal_chat': 'Messagerie interne',
            'ai_leak': 'IA',
        }

        type_average_scores = {}

        for type_key, scores in dept_data['type_scores'].items():
            if scores:
                type_average_scores[type_key] = round(sum(scores) / len(scores))
            else:
                type_average_scores[type_key] = 0

        max_type_score = max(type_average_scores.values())

        dominant_types = [
            type_labels[type_key]
            for type_key, type_score in type_average_scores.items()
            if type_score == max_type_score and type_score > 0
        ]

        if not dominant_types:
            dominant_risk = "Aucun"

        elif len(dominant_types) == 1:
            dominant_risk = dominant_types[0]

        elif len(dominant_types) == len(type_labels):
            dominant_risk = "Équilibré"

        else:
            dominant_risk = " + ".join(dominant_types)
        department_rows.append({
            'department': dept_data['department'],
            'participants': len(dept_data['participants']),
            'total_employees': total_department_employees,
            'score': score,
            'status_label': status_label,
            'badge_class': badge_class,
            'dominant_risk': dominant_risk,
        })

    department_rows = sorted(
        department_rows,
        key=lambda item: item['score'],
        reverse=True
    )
    if sort_score == 'desc':
        rows = sorted(
            rows,
            key=lambda item: item['score'] if item['score'] is not None else -1,
            reverse=True
        )

    elif sort_score == 'asc':
        rows = sorted(
            rows,
            key=lambda item: item['score'] if item['score'] is not None else 999
        )
    return render(request, 'announced_drills/campaign_results_detail.html', {
        'campaign': campaign,
        'rows': rows,
        'department_rows': department_rows,
        'sort_score': sort_score,
    })

def parse_items(text_block):
    if not text_block:
        return []
    # return [line.strip().lower() for line in text_block.splitlines() if line.strip()]
    items = []

    for line in text_block.splitlines():
        parts = line.split(',')

        for part in parts:
            cleaned = part.strip().lower()

            if cleaned:
                items.append(cleaned)

    return items


def compute_ai_risk_from_scenario_fields(scenario, submitted_text, attached_file_name=""):
    combined_text = f"{submitted_text} {attached_file_name}".strip()

    if not combined_text:
        return "safe"

    text = combined_text.lower()

    risk_items = parse_items(scenario.risk_items)
    warning_items = parse_items(scenario.warning_items)

    for item in risk_items:
        if item in text:
            return "risk"

    for item in warning_items:
        if item in text:
            return "warning"

    return "safe"


def get_department_choices():
    departments = (
        Employee.objects
        .exclude(department__isnull=True)
        .exclude(department__exact='')
        .values_list('department', flat=True)
        .distinct()
        .order_by('department')
    )

    return [('all', 'Tous les employés')] + [(dep, dep) for dep in departments]

def scenario_matches_campaign_department(scenario, campaign_departments):
    scenario_departments = scenario.target_departments or ['all']

    if 'all' in scenario_departments:
        return True

    if 'all' in campaign_departments:
        return True

    return any(dep in scenario_departments for dep in campaign_departments)


def get_campaign_target_employees(campaign):
    departments = campaign.target_departments or ['all']

    employees = Employee.objects.exclude(
        email__isnull=True
    ).exclude(
        email__exact=''
    )

    if 'all' not in departments:
        employees = employees.filter(department__in=departments)

    return employees


def send_campaign_to_employees(request, campaign):
    employees = get_campaign_target_employees(campaign)

    sent_count = 0

    for employee in employees:
        # campaign_link = request.build_absolute_uri(campaign.start_link)
        if request:
            campaign_link = request.build_absolute_uri(
                campaign.start_link
            )
        else:
            campaign_link = f"http://127.0.0.1:8000{campaign.start_link}"

        send_mail(
            subject=f"Campagne de sensibilisation - {campaign.campaign_name}",
            message=(
                f"Bonjour {employee.full_name},\n\n"
                f"Vous êtes invité(e) à participer à une campagne de sensibilisation cybersécurité.\n\n"
                f"Lien : {campaign_link}\n\n"
                f"Merci de compléter les scénarios avant expiration."
            ),
            from_email=None,
            recipient_list=[employee.email],
            fail_silently=False,
        )

        sent_count += 1

    campaign.sent_at = timezone.now()
    campaign.status = 'sent'
    campaign.save()

    return sent_count
@login_required(login_url='login')
def send_campaign_emails(request, run_id):
    campaign = get_object_or_404(CampaignRun, id=run_id)

    if campaign.status == 'expired':
        return redirect('announced-campaign-home')

    send_campaign_to_employees(request, campaign)

    return render(request, 'announced_drills/campaign_home.html', {
        'scenario_count': Scenario.objects.filter(is_active=True).count(),
        'departments': get_department_choices(),
        'success_message': "Campagne envoyée aux employés avec succès.",
        'generated_run': campaign,
    })
def campaign_home(request):
    scenario_count = Scenario.objects.filter(is_active=True).count()
    departments = get_department_choices()

    if request.method == 'POST':
        campaign_name = request.POST.get('campaign_name', '').strip()
        question_count = request.POST.get('question_count', '10')
        target_departments = request.POST.getlist('target_departments')
        delivery_mode = request.POST.get('delivery_mode', 'manual')
        scheduled_at_raw = request.POST.get('scheduled_at', '').strip()
        validity_value = request.POST.get('validity_value', '7')
        validity_unit = request.POST.get('validity_unit', 'days')
        print("VALIDITY =", validity_value, validity_unit)

        try:
            validity_value = int(validity_value)
        except ValueError:
            validity_value = 7

        if validity_value < 1:
            validity_value = 1

        if validity_unit == 'minutes':
            validity_delta = timedelta(minutes=validity_value)
        elif validity_unit == 'hours':
            validity_delta = timedelta(hours=validity_value)
        else:
            validity_delta = timedelta(days=validity_value)
        scheduled_at = None

        if delivery_mode == 'scheduled':
            scheduled_at = parse_datetime(scheduled_at_raw)

            if not scheduled_at:
                return render(request, 'announced_drills/campaign_home.html', {
                    'scenario_count': scenario_count,
                    'departments': departments,
                    'error_message': "Veuillez choisir une date d’envoi valide.",
                    'form_campaign_name': campaign_name,
                    'form_question_count': question_count,
                    'form_target_departments': target_departments,
                })

        if not target_departments:
            return render(request, 'announced_drills/campaign_home.html', {
                'scenario_count': scenario_count,
                'departments': departments,
                'error_message': "Veuillez sélectionner au moins un département.",
                'form_campaign_name': campaign_name,
                'form_question_count': question_count,
                'form_target_departments': target_departments,
            })

        if 'all' in target_departments and len(target_departments) > 1:
            target_departments = ['all']
        if not campaign_name:
            campaign_name = generate_campaign_name(target_departments)


        try:
            question_count = int(question_count)
        except ValueError:
            question_count = 10

        if question_count < 1:
            question_count = 1

        if not Scenario.objects.filter(is_active=True).exists():
            return render(request, 'announced_drills/campaign_home.html', {
                'scenario_count': scenario_count,
                'departments': departments,
                'error_message': "Aucun scénario actif disponible.",
                'form_campaign_name': campaign_name,
                'form_question_count': question_count,
                'form_target_departments': target_departments,
            })

        # run = CampaignRun.objects.create(
        #     campaign_name=campaign_name,
        #     target_departments=target_departments,
        #     question_count=question_count,
        #     status='ready'
        # )
        if delivery_mode == 'scheduled':
            campaign_status = 'scheduled'
            expires_at = scheduled_at + validity_delta
        else:
            campaign_status = 'ready'
            expires_at = timezone.now() + validity_delta

        run = CampaignRun.objects.create(
            campaign_name=campaign_name,
            target_departments=target_departments,
            question_count=question_count,
            delivery_mode=delivery_mode,
            scheduled_at=scheduled_at,
            expires_at=expires_at,
            validity_days=validity_value if validity_unit == 'days' else 1,
            status=campaign_status,
        )
        signer = Signer()
        signed_token = signer.sign(str(run.id))
        run.start_link = f"/announced_drills/start/{run.id}/{signed_token}/"        # run.start_link = f"/announced-drills/start/{run.id}/"
        run.save()

        return render(request, 'announced_drills/campaign_home.html', {
            'scenario_count': scenario_count,
            'departments': departments,
            'success_message': "Campagne générée avec succès.",
            'generated_run': run,
            'form_campaign_name': campaign_name,
            'form_question_count': question_count,
            'form_target_departments': target_departments,
        })

    return render(request, 'announced_drills/campaign_home.html', {
        'scenario_count': scenario_count,
        'departments': departments,
    })

def generate_campaign_name(target_departments):
    today = datetime.now().strftime("%d/%m/%y")

    if 'all' in target_departments:
        base_name = f"Campagne Globale - {today}"
    elif len(target_departments) == 1:
        base_name = f"Campagne {target_departments[0]} - {today}"
    else:
        base_name = f"Campagne Multiple - {today}"

    existing_count = CampaignRun.objects.filter(
        campaign_name__startswith=base_name
    ).count()

    if existing_count == 0:
        return base_name

    return f"{base_name} ({existing_count + 1})"

# def user_start(request, run_id):
#     run = get_object_or_404(CampaignRun, id=run_id)
def user_start(request, run_id, signed_token):
    signer = Signer()

    try:
        original_run_id = signer.unsign(signed_token)

        if str(run_id) != original_run_id:
            return render(request, 'announced_drills/user_start.html', {
                'error_message': "Lien invalide ou modifié.",
            })

    except BadSignature:
        return render(request, 'announced_drills/user_start.html', {
            'error_message': "Lien invalide ou modifié.",
        })

    run = get_object_or_404(CampaignRun, id=run_id)
    now = timezone.now()

    if run.scheduled_at and now < run.scheduled_at:
        return render(request, 'announced_drills/user_start.html', {
            'run': run,
            'scenario_count': run.question_count,
            'error_message': "Cette campagne n’est pas encore disponible.",
        })

    if run.expires_at and now > run.expires_at:
        run.status = 'expired'
        run.save()

        return render(request, 'announced_drills/user_start.html', {
            'run': run,
            'scenario_count': run.question_count,
            'error_message': "Cette campagne a expiré.",
        })
    if request.method == 'POST':
        # Nettoyer une ancienne tentative
        request.session.pop('employee_id', None)

        full_name = request.POST.get('full_name', '').strip()

        if not full_name:
            return render(request, 'announced_drills/user_start.html', {
                'run': run,
                'scenario_count': run.question_count,
                'error_message': "Veuillez saisir votre nom complet.",
            })

        employee = Employee.objects.filter(full_name__iexact=full_name).first()
        already_participated = ScenarioResponse.objects.filter(
            campaign_run=run,
            employee=employee
        ).exists()

        if already_participated:
            return render(request, 'announced_drills/user_start.html', {
                'run': run,
                'scenario_count': run.question_count,
                'error_message': "Vous avez déjà participé à cette campagne.",
            })
        if not employee:
            return render(request, 'announced_drills/user_start.html', {
                'run': run,
                'scenario_count': run.question_count,
                'error_message': "Employé introuvable. Vérifiez le nom saisi.",
            })

        request.session['employee_id'] = employee.id
        request.session.modified = True

        return redirect('announced-campaign-launch', run_id=run.id)

    return render(request, 'announced_drills/user_start.html', {
        'run': run,
        'scenario_count': run.question_count,
    })

def scenario_matches_employee_department(scenario, employee_department):
    targets = scenario.target_departments or ['all']

    if 'all' in targets:
        return True

    return employee_department in targets

def launch_campaign(request, run_id):
    run = get_object_or_404(CampaignRun, id=run_id)
    now = timezone.now()

    if run.scheduled_at and now < run.scheduled_at:
        return render(request, 'announced_drills/user_start.html', {
            'run': run,
            'scenario_count': run.question_count,
            'error_message': "Cette campagne n’est pas encore disponible.",
        })

    if run.expires_at and now > run.expires_at:
        run.status = 'expired'
        run.save()

        return render(request, 'announced_drills/user_start.html', {
            'run': run,
            'scenario_count': run.question_count,
            'error_message': "Cette campagne a expiré.",
        })

    employee_id = request.session.get('employee_id')

    if not employee_id:
        signer = Signer()
        signed_token = signer.sign(str(run.id))

        return redirect(
            'announced-campaign-start',
            run_id=run.id,
            signed_token=signed_token
        )

    employee = get_object_or_404(Employee, id=employee_id)
    employee_department = employee.department

    campaign_departments = run.target_departments or ['all']

    if 'all' not in campaign_departments and employee_department not in campaign_departments:
        request.session.pop('employee_id', None)
        request.session.modified = True

        return render(request, 'announced_drills/user_start.html', {
            'run': run,
            'scenario_count': run.question_count,
            'error_message': "Vous ne faites pas partie des départements ciblés par cette campagne.",
        })
    CampaignScenario.objects.filter(campaign_run=run).delete()

    all_active_scenarios = Scenario.objects.filter(is_active=True)

    eligible_scenarios = [
        scenario for scenario in all_active_scenarios
        if scenario_matches_employee_department(scenario, employee_department)
    ]
    required_types = ['phishing', 'ai_leak', 'internal_chat']

    selected = []

    # 1 scénario minimum par type important
    for scenario_type in required_types:
        scenarios_of_type = [
            scenario for scenario in eligible_scenarios
            if scenario.scenario_type == scenario_type
        ]

        if scenarios_of_type:
            selected.append(random.choice(scenarios_of_type))

    # éviter les doublons
    selected_ids = {scenario.id for scenario in selected}

    remaining_scenarios = [
        scenario for scenario in eligible_scenarios
        if scenario.id not in selected_ids
    ]

    random.shuffle(remaining_scenarios)

    remaining_needed = run.question_count - len(selected)

    if remaining_needed > 0:
        selected += remaining_scenarios[:remaining_needed]

    # si le nombre demandé est plus petit que 3
    selected = selected[:run.question_count]

    random.shuffle(selected)


    for index, scenario in enumerate(selected, start=1):
        CampaignScenario.objects.create(
            campaign_run=run,
            scenario=scenario,
            order_index=index
        )

    run.status = 'running'
    run.save()

    return redirect('announced-scenario-runner', run_id=run.id, position=1)

@never_cache
def scenario_runner(request, run_id, position):
    run = get_object_or_404(CampaignRun, id=run_id)
    if run.expires_at and timezone.now() > run.expires_at:
        run.status = 'expired'
        run.save()

        request.session.pop('employee_id', None)
        request.session.modified = True

        return render(request, 'announced_drills/user_start.html', {
            'run': run,
            'scenario_count': run.question_count,
            'error_message': "Cette campagne a expiré. Vous ne pouvez plus continuer le test.",
        })
    ordered_scenarios = run.campaign_scenarios.all()
    if position > ordered_scenarios.count():
        run.status = 'completed'
        run.save()
        return redirect('announced-campaign-complete', run_id=run.id)

    campaign_scenario = ordered_scenarios[position - 1]
    scenario = campaign_scenario.scenario
    employee_id = request.session.get('employee_id')

    already_answered = ScenarioResponse.objects.filter(
        campaign_run=run,
        scenario=scenario,
        employee_id=employee_id
    ).exists()

    if already_answered:
        return redirect(
            'announced-scenario-runner',
            run_id=run.id,
            position=position + 1
        )

    if request.method == 'POST':
        action_taken = request.POST.get('action_taken', 'no_action')
        time_taken = int(request.POST.get('time_taken', 0))
        submitted_text = (
            request.POST.get('ai_text', '') or
            request.POST.get('chat_text', '')
        ).strip()
        attached_file_name = request.POST.get('attached_file_name', '').strip()
        # Cas IA et chat : scoring basé sur les données sensibles définies dans l’admin
        if scenario.ui_mode in ['ai_prompt', 'chat']:
            risk_result = compute_ai_risk_from_scenario_fields(scenario, submitted_text,attached_file_name)
        # Cas normal : phishing, document, partage, etc.
        else:
            selected_action = scenario.actions.filter(action_value=action_taken).first()

            if selected_action:
                risk_result = selected_action.risk_result
            else:
                risk_result = 'warning'
        employee = None
        employee_id = request.session.get('employee_id')

        if employee_id:
            employee = Employee.objects.filter(id=employee_id).first()
        ScenarioResponse.objects.create(
            campaign_run=run,
            scenario=scenario,
            employee=employee,
            action_taken=action_taken,
            risk_result=risk_result,
            time_taken=time_taken,
            submitted_text=submitted_text,
            attached_file_name=attached_file_name,
        )
        # if employee:
        #     update_campaign_employee_result(run, employee)
        if employee:

            employee_response_count = ScenarioResponse.objects.filter(
                campaign_run=run,
                employee=employee
            ).count()

            total_scenarios = run.campaign_scenarios.count()

            if employee_response_count >= total_scenarios:
                update_campaign_employee_result(run, employee)
        return redirect('announced-scenario-runner', run_id=run.id, position=position + 1)
    actions = scenario.actions.all().order_by('order_index')
    return render(request, 'announced_drills/scenario_runner.html', {
        'run': run,
        'scenario': scenario,
        'position': position,
        'total': ordered_scenarios.count(),
        'actions': actions,
    })


def campaign_complete(request, run_id):
    run = get_object_or_404(CampaignRun, id=run_id)
    responses = ScenarioResponse.objects.filter(campaign_run=run)

    safe_count = responses.filter(risk_result='safe').count()
    warning_count = responses.filter(risk_result='warning').count()
    risk_count = responses.filter(risk_result='risk').count()

    return render(request, 'announced_drills/campaign_complete.html', {
        'run': run,
        'responses': responses,
        'safe_count': safe_count,
        'warning_count': warning_count,
        'risk_count': risk_count,
    })

@login_required(login_url='login')
def global_statistics(request):
    period = request.GET.get('period', '30d')
    selected_department = request.GET.get('department', 'all')
    selected_campaign = request.GET.get('campaign', 'all')

    period_start = get_period_start(period)

    departments = get_department_choices()
    campaigns = CampaignRun.objects.all().order_by('-created_at')

    filtered_campaigns = campaigns

    if period_start:
        filtered_campaigns = filtered_campaigns.filter(created_at__gte=period_start)

    if selected_campaign != 'all':
        filtered_campaigns = filtered_campaigns.filter(id=selected_campaign)

    responses = ScenarioResponse.objects.filter(
        campaign_run__in=filtered_campaigns
    ).exclude(employee__isnull=True)

    if selected_department != 'all':
        responses = responses.filter(employee__department=selected_department)

    completed_employee_scores = []
    department_scores = {}
    for value, label in departments:
        if value != 'all':
            department_scores[label] = []
    category_scores = {
        'Phishing': [],
        'Messagerie interne': [],
        'Fuite IA': [],
    }
    risk_level_counts = {
        'Aucun risque': 0,
        'Risque faible': 0,
        'Risque modéré': 0,
        'Risque élevé': 0,
        'Très risqué': 0,
    }

    heatmap_scores = {}
    for value, label in departments:
        if value != 'all':
            heatmap_scores[label] = {
                'Phishing': [],
                'Messagerie interne': [],
                'Fuite IA': [],
            }

    employee_risk_rows = []
    timeline_scores = {}

    status_counts = {
        'Terminé': 0,
        'En cours': 0,
        'Non complété': 0,
        'Non participé': 0,
    }

    for campaign in filtered_campaigns.order_by('created_at'):
        campaign_responses = responses.filter(campaign_run=campaign)

        employee_ids = (
            campaign_responses
            .values_list('employee_id', flat=True)
            .distinct()
        )

        total_scenarios = campaign.campaign_scenarios.count()

        if total_scenarios == 0:
            total_scenarios = campaign.question_count

        for employee_id in employee_ids:
            employee_responses = campaign_responses.filter(employee_id=employee_id)
            total = employee_responses.count()

            if total == 0:
                status_counts['Non participé'] += 1
                continue

            if total < total_scenarios:

                if campaign.status in ['expired', 'completed']:
                    status_counts['Non complété'] += 1
                else:
                    status_counts['En cours'] += 1

                continue

            status_counts['Terminé'] += 1

            employee = Employee.objects.filter(id=employee_id).first()

            if not employee:
                continue

            safe_count = employee_responses.filter(risk_result='safe').count()
            warning_count = employee_responses.filter(risk_result='warning').count()
            risk_count = employee_responses.filter(risk_result='risk').count()

            score = calculate_score_from_counts(
                safe_count,
                warning_count,
                risk_count
            )

            completed_employee_scores.append(score)
            # Répartition des niveaux de risque
            if score == 0:
                risk_level_counts['Aucun risque'] += 1
            elif score <= 33:
                risk_level_counts['Risque faible'] += 1
            elif score <= 66:
                risk_level_counts['Risque modéré'] += 1
            elif score <= 99:
                risk_level_counts['Risque élevé'] += 1
            else:
                risk_level_counts['Très risqué'] += 1
            campaign_date = campaign.created_at.strftime('%d/%m')

            if campaign_date not in timeline_scores:
                timeline_scores[campaign_date] = []

            timeline_scores[campaign_date].append(score)

            department = employee.department or 'Non assigné'

            if department not in department_scores:
                department_scores[department] = []

            department_scores[department].append(score)

            for scenario_type, label in {
                'phishing': 'Phishing',
                'internal_chat': 'Messagerie interne',
                'ai_leak': 'Fuite IA',
            }.items():
                type_responses = employee_responses.filter(
                    scenario__scenario_type=scenario_type
                )

                if type_responses.exists():
                    type_score = calculate_score_from_counts(
                        type_responses.filter(risk_result='safe').count(),
                        type_responses.filter(risk_result='warning').count(),
                        type_responses.filter(risk_result='risk').count()
                    )

                    category_scores[label].append(type_score)
                    # Heatmap département × catégorie
                    department = employee.department or 'Non assigné'

                    if department not in heatmap_scores:
                        heatmap_scores[department] = {
                            'Phishing': [],
                            'Messagerie interne': [],
                            'Fuite IA': [],
                        }

                    heatmap_scores[department][label].append(type_score)
            employee_risk_rows.append({
                'employee': employee,
                'campaign': campaign,
                'score': score,
                'safe_count': safe_count,
                'warning_count': warning_count,
                'risk_count': risk_count,
            })

    average_score = (
        round(sum(completed_employee_scores) / len(completed_employee_scores))
        if completed_employee_scores else 0
    )

    completed_count = len(completed_employee_scores)

    targeted_count = 0

    for campaign in filtered_campaigns:
        target_departments = campaign.target_departments or ['all']

        if selected_department != 'all':
            targeted_count += Employee.objects.filter(
                department=selected_department
            ).count()
        elif 'all' in target_departments:
            targeted_count += Employee.objects.exclude(
                department__isnull=True
            ).exclude(
                department__exact=''
            ).count()
        else:
            targeted_count += Employee.objects.filter(
                department__in=target_departments
            ).count()

    completion_rate = (
        round((completed_count / targeted_count) * 100)
        if targeted_count else 0
    )

    department_chart = []

    for department, scores in department_scores.items():
        department_chart.append({
            'label': department,
            'score': round(sum(scores) / len(scores)) if scores else 0,
        })

    department_chart = sorted(
        department_chart,
        key=lambda item: item['score'],
        reverse=True
    )

    category_chart = []

    for label, scores in category_scores.items():
        category_chart.append({
            'label': label,
            'score': round(sum(scores) / len(scores)) if scores else 0,
        })
    timeline_chart = []

    # =========================
    # ÉVOLUTION TEMPORELLE
    # =========================

    timeline_scores = {}
    department_timeline_scores = {}

    for campaign in filtered_campaigns:
        campaign_responses = responses.filter(campaign_run=campaign)

        total_scenarios = campaign.campaign_scenarios.count()
        if total_scenarios == 0:
            total_scenarios = campaign.question_count

        campaign_label = campaign.created_at.strftime('%d/%m %H:%M')

        employee_ids = (
            campaign_responses
            .values_list('employee_id', flat=True)
            .distinct()
        )

        for employee_id in employee_ids:
            employee = Employee.objects.filter(id=employee_id).first()

            if not employee:
                continue

            employee_responses = campaign_responses.filter(
                employee_id=employee_id
            )

            if employee_responses.count() < total_scenarios:
                continue

            score = calculate_score_from_counts(
                employee_responses.filter(risk_result='safe').count(),
                employee_responses.filter(risk_result='warning').count(),
                employee_responses.filter(risk_result='risk').count()
            )

            timeline_scores.setdefault(campaign_label, []).append(score)

            department = employee.department or 'Non assigné'

            department_timeline_scores.setdefault(department, {})
            department_timeline_scores[department].setdefault(campaign_label, [])
            department_timeline_scores[department][campaign_label].append(score)

    timeline_labels = list(timeline_scores.keys())

    timeline_values = [
        round(sum(scores) / len(scores))
        for scores in timeline_scores.values()
    ]

    department_lines = []

    for department, values_by_date in department_timeline_scores.items():
        department_lines.append({
            'label': department,
            'data': [
                round(sum(values_by_date[label]) / len(values_by_date[label]))
                if label in values_by_date else None
                for label in timeline_labels
            ]
        })
    # most_risky_department = (
    #     department_chart[0]['label']
    #     if department_chart else 'Aucun'
    # )

    # most_risky_category = max(
    #     category_chart,
    #     key=lambda item: item['score']
    # )['label'] if category_chart else 'Aucune'
    non_empty_departments = [
        item for item in department_chart
        if item['score'] > 0
    ]

    if selected_department != 'all':
        selected_department_score = next(
            (
                item['score']
                for item in department_chart
                if item['label'] == selected_department
            ),
            0
        )

        if selected_department_score > 0:
            most_risky_department = selected_department
        else:
            most_risky_department = 'Aucune donnée'
    else:
        most_risky_department = (
            non_empty_departments[0]['label']
            if non_empty_departments else 'Aucune donnée'
        )


    non_empty_categories = [
        item for item in category_chart
        if item['score'] > 0
    ]

    most_risky_category = (
        max(non_empty_categories, key=lambda item: item['score'])['label']
        if non_empty_categories else 'Aucune donnée'
    )

    top_risky_employees = sorted(
        employee_risk_rows,
        key=lambda item: item['score'],
        reverse=True
    )[:5]
    heatmap_rows = []

    for department, categories in heatmap_scores.items():
        heatmap_rows.append({
            'department': department,
            'phishing': round(sum(categories['Phishing']) / len(categories['Phishing'])) if categories['Phishing'] else 0,
            'messagerie': round(sum(categories['Messagerie interne']) / len(categories['Messagerie interne'])) if categories['Messagerie interne'] else 0,
            'ia': round(sum(categories['Fuite IA']) / len(categories['Fuite IA'])) if categories['Fuite IA'] else 0,
        })


    # Tendance globale simple
    trend_label = "Stable"
    trend_value = 0

    if len(timeline_values) >= 2:
        first_score = timeline_values[0]
        last_score = timeline_values[-1]
        trend_value = last_score - first_score

        if trend_value < 0:
            trend_label = "En baisse"
        elif trend_value > 0:
            trend_label = "En hausse"
    return render(request, 'announced_drills/global_statistics.html', {
        'period': period,
        'selected_department': selected_department,
        'selected_campaign': selected_campaign,
        'departments': departments,
        'campaigns': campaigns,

        'average_score': average_score,
        'completion_rate': completion_rate,
        'completed_count': completed_count,
        'targeted_count': targeted_count,
        'most_risky_department': most_risky_department,
        'most_risky_category': most_risky_category,

        'department_chart': department_chart,
        'category_chart': category_chart,
        'top_risky_employees': top_risky_employees,
        # 'timeline_chart': timeline_chart,
        'status_counts': status_counts,
        'top_risky_employees': top_risky_employees,
        'timeline_labels_json': json.dumps(timeline_labels),
        'timeline_values_json': json.dumps(timeline_values),
        'department_lines_json': json.dumps(department_lines),
        'risk_level_counts': risk_level_counts,
        'heatmap_rows': heatmap_rows,
        'trend_label': trend_label,
        'trend_value': trend_value,
    })