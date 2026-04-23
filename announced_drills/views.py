import random
from django.shortcuts import get_object_or_404, redirect, render
from .models import CampaignRun, CampaignScenario, Scenario, ScenarioResponse

def parse_items(text_block):
    if not text_block:
        return []
    return [line.strip().lower() for line in text_block.splitlines() if line.strip()]


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

DEPARTMENT_CHOICES = [
    ('all', 'Tous les employés'),
    ('rh', 'Ressources humaines'),
    ('finance', 'Finance'),
    ('it', 'Informatique'),
    ('marketing', 'Marketing'),
    ('engineering', 'Ingénierie'),
]


def campaign_home(request):
    scenario_count = Scenario.objects.filter(is_active=True).count()

    if request.method == 'POST':
        campaign_name = request.POST.get('campaign_name', '').strip()
        target_department = request.POST.get('target_department', 'all')
        question_count = request.POST.get('question_count', '10')

        if not campaign_name:
            return render(request, 'announced_drills/campaign_home.html', {
                'scenario_count': scenario_count,
                'departments': DEPARTMENT_CHOICES,
                'error_message': "Veuillez saisir un nom pour la campagne.",
            })

        try:
            question_count = int(question_count)
        except ValueError:
            question_count = 10

        if question_count < 1:
            question_count = 1

        active_scenarios = list(Scenario.objects.filter(is_active=True))

        if len(active_scenarios) < question_count:
            return render(request, 'announced_drills/campaign_home.html', {
                'scenario_count': scenario_count,
                'departments': DEPARTMENT_CHOICES,
                'error_message': f"Vous avez seulement {len(active_scenarios)} scénarios actifs. Impossible de générer une campagne de {question_count} tests.",
            })

        random.shuffle(active_scenarios)
        selected = active_scenarios[:question_count]

        run = CampaignRun.objects.create(
            campaign_name=campaign_name,
            target_department=target_department,
            question_count=question_count,
            status='ready'
        )

        for index, scenario in enumerate(selected, start=1):
            CampaignScenario.objects.create(
                campaign_run=run,
                scenario=scenario,
                order_index=index
            )

        run.start_link = f"/announced-drills/start/{run.id}/"
        run.save()

        return render(request, 'announced_drills/campaign_home.html', {
            'scenario_count': scenario_count,
            'departments': DEPARTMENT_CHOICES,
            'success_message': "Campagne générée avec succès.",
            'generated_run': run,
        })

    return render(request, 'announced_drills/campaign_home.html', {
        'scenario_count': scenario_count,
        'departments': DEPARTMENT_CHOICES,
    })


def user_start(request, run_id):
    run = get_object_or_404(CampaignRun, id=run_id)

    return render(request, 'announced_drills/user_start.html', {
        'run': run,
        'scenario_count': run.question_count,
    })


def launch_campaign(request, run_id):
    run = get_object_or_404(CampaignRun, id=run_id)
    run.status = 'running'
    run.save()

    return redirect('announced-scenario-runner', run_id=run.id, position=1)


def scenario_runner(request, run_id, position):
    run = get_object_or_404(CampaignRun, id=run_id)
    ordered_scenarios = run.campaign_scenarios.all()
    if position > ordered_scenarios.count():
        run.status = 'completed'
        run.save()
        return redirect('announced-campaign-complete', run_id=run.id)

    campaign_scenario = ordered_scenarios[position - 1]
    scenario = campaign_scenario.scenario

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

        ScenarioResponse.objects.create(
            campaign_run=run,
            scenario=scenario,
            action_taken=action_taken,
            risk_result=risk_result,
            time_taken=time_taken,
            submitted_text=submitted_text,
            attached_file_name=attached_file_name,

        )
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