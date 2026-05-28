from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Avg, Count, Q
from django.contrib import messages
from .models import EmployeeRiskProfile
from core.models import Employee

# =====================================================================
#  1. VUE DU DASHBOARD GLOBAL (CAMPAGNE - VISUALISATION ENSEMBLE)
# =====================================================================

def campaign_dashboard_view(request):
    """
    Vue principale qui agrège les données de tous les profils pour générer
    les métriques globales de la campagne et gère l'action POST de synchronisation.
    """
    
    # ─── GESTION DES BOUTONS (REQUÊTES POST) ───
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'refresh':
            # Code exécuté pour "Synchroniser la Matrice" (ex: seed_data.run())
            messages.success(request, "La matrice cyber-cognitive a été resynchronisée avec succès.")
            
        # Redirection PRG (Post-Redirect-Get) pour éviter le renvoi du formulaire au rafraîchissement
        return redirect(request.path_info)

    # ─── LOGIQUE DE CHARGEMENT DU DASHBOARD (REQUÊTES GET) ───
    
    # 1. Récupération de tous les profils de risques calculés
    profiles = EmployeeRiskProfile.objects.all()
    total_agents = profiles.count()

    if total_agents == 0:
        return render(request, 'ml_engine/campaign_dashboard.html', {'empty': True})

    # 2. Calcul des variables de la Campagne Globale (Moyennes)
    campaign_metrics = profiles.aggregate(
        avg_honey=Avg('honeytoken_score'),
        avg_ai=Avg('ai_score'),
        avg_azk=Avg('azk_score'),
        avg_global=Avg('global_score')
    )

    global_risk_score = round(campaign_metrics['avg_global'] or 0, 2)

    # Attribution du label global de la campagne
    if global_risk_score < 25.0:
        global_risk_label = "LOW"
    elif global_risk_score < 50.0:
        global_risk_label = "MEDIUM"
    elif global_risk_score < 75.0:
        global_risk_label = "HIGH"
    else:
        global_risk_label = "CRITICAL"

    # Distribution des labels pour les graphiques du Dashboard
    risk_distribution = profiles.values('risk_label').annotate(count=Count('risk_label'))

    # 3. Analyse par département & génération des recommandations
    departments_query = profiles.values('department').annotate(
        avg_score=Avg('global_score'),
        total=Count('id')
    ).order_by('-avg_score')

    departments_summary = []
    for dept in departments_query:
        dept_name = dept['department']
        avg_score = round(dept['avg_score'] or 0, 2)
        
        # Trouver le profil psychologique dominant dans ce département (Mode)
        profils_dept = profiles.filter(department=dept_name).values_list('profiling_label', flat=True)
        profil_dominant = max(set(profils_dept), key=list(profils_dept).count) if profils_dept else "SECURE"

        # Logique d'attribution des recommandations par département
        if avg_score >= 65:
            recommendation = (f"🚨 ALERTE CRITIQUE : Le département {dept_name} présente des vulnérabilités critiques. "
                              f"Action requise : Déclenchement immédiat d'une cellule de remédiation cyber sous 48h. "
                              f"Restriction temporaire des droits d'accès aux services externes non validés.")
            status_color = "danger"
        elif 40 <= avg_score < 65:
            if profil_dominant == "GOOD KNOWLEDGE BUT RISKLY BEHAVIOR":
                recommendation = (f"⚠️ VIGILANCE : Le personnel de {dept_name} connaît la théorie mais agit de façon impulsive. "
                                  f"Action requise : Mettre en place des verrous UI ou des pop-ups d'avertissement contextuels.")
            else:
                recommendation = (f"⚠️ VIGILANCE : Le département {dept_name} manque de connaissances fondamentales. "
                                  f"Action requise : Inscription automatique des équipes à une micro-formation obligatoire.")
            status_color = "warning"
        else:
            recommendation = (f"🛡️ SÉCURISÉ : Excellente posture pour le département {dept_name}. "
                              f"Action requise : Nomination d'un référent 'Cyber-Ambassadeur' pour maintenir ce niveau.")
            status_color = "success"

        departments_summary.append({
            'name': dept_name,
            'avg_score': avg_score,
            'total_employees': dept['total'],
            'profil_dominant': profil_dominant,
            'recommendation': recommendation,
            'status_color': status_color
        })

    # Context dynamique à envoyer au template HTML
    context = {
        'empty': False,
        'global_metrics': {
            'honeytoken_risk_score': round(campaign_metrics['avg_honey'] or 0, 2),
            'ai_risk_score': round(campaign_metrics['avg_ai'] or 0, 2),
            'azk_risk_score': round(campaign_metrics['avg_azk'] or 0, 2),
            'global_risk_score': global_risk_score,
            'global_risk_label': global_risk_label,
            'total_agents': total_agents
        },
        'risk_distribution': risk_distribution,
        'departments_summary': departments_summary,
        'recent_critical_profiles': profiles.filter(risk_label__in=['HIGH', 'CRITICAL']).order_by('-global_score')[:5]
    }

    return render(request, 'ml_engine/campaign_dashboard.html', context)


# =====================================================================
#  2. VUE DU PROFIL DE RISQUE INDIVIDUEL (AGENT DETAIL)
# =====================================================================

def agent_detail_view(request, agent_uuid):
    """
    Vue détaillée affichant l'analyse complète pour un employé spécifique via son UUID unique.
    """
    profile = get_object_or_404(EmployeeRiskProfile, user_uuid=agent_uuid)
    employee_info = Employee.objects.filter(department=profile.department).first()

    color_map = {
        "LOW": "success",
        "MEDIUM": "info",
        "HIGH": "warning",
        "CRITICAL": "danger"
    }
    badge_color = color_map.get(profile.risk_label, "secondary")

    context = {
        'profile': profile,
        'employee_info': employee_info,
        'badge_color': badge_color
    }
    
    return render(request, 'ml_engine/agent_detail.html', context)