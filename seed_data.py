import os
import django
import json
import random
import uuid

# Configuration de l'environnement Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cognisec.settings')
django.setup()

from core.models import Employee
from ml_engine.models import EmployeeRiskProfile

# Importation des structures du modèle cyber-comportemental centralisé
# (Assure-toi que le code précédent est bien enregistré dans ml_engine/models.py ou un fichier accessible)
from ml_engine.models import PsycheSentinelModel, SimulationInputData

print("=== Génération complète des profils (Modèle Unique Évolué) ===")

# Chargement du fichier JSON avec l'encodage Windows UTF-16
with open("initial_employees.json", "r", encoding="utf-16") as f:
    employees_data = json.load(f)

# Nettoyage des anciennes données pour repartir sur une base propre
EmployeeRiskProfile.objects.all().delete()
Employee.objects.all().delete()

# Instanciation du vrai modèle
model_cyber = PsycheSentinelModel()

for emp in employees_data:
    f = emp["fields"]

    # 1. Insertion dans l'annuaire de base (Employee)
    Employee.objects.create(
        sam_account_name=f["sam_account_name"],
        full_name=f["full_name"],
        email=f["email"],
        department=f["department"],
        hrn_score=f["hrn_score"],
        drill_progress=f["drill_progress"],
        last_event=f["last_event"],
        status=f["status"]
    )

    # 2. SIMULATION RÉALISTE DES ENTRÉES (Pour alimenter Ouiame & Aïcha)
    # On génère des comportements plausibles au lieu de scores magiques aléatoires
    total_scenarios = random.randint(3, 6)
    risk_count = random.randint(0, total_scenarios)
    safe_count = total_scenarios - risk_count
    
    mock_ouiame_inputs = {
        'employee.department': f["department"],
        'ScenarioResponse.action_taken': 'cliquer' if risk_count > 1 else 'ignore',
        'ScenarioResponse.risk_result': 'risk' if risk_count > 1 else 'safe',
        'ScenarioResponse.time_taken': round(random.uniform(5.0, 60.0), 1),
        'CampaignEmployeeResult.total_count': total_scenarios,
        'CampaignEmployeeResult.safe_count': safe_count,
        'CampaignEmployeeResult.warning_count': 0,
        'CampaignEmployeeResult.risk_count': risk_count,
        'categories_detail': [
            {'scenario_type': 'phishing', 'score': round(random.uniform(10, 100), 1)},
            {'scenario_type': 'ai_leak', 'score': round(random.uniform(10, 100), 1)},
            {'scenario_type': 'document', 'score': round(random.uniform(10, 100), 1)}
        ]
    }

    mock_aicha_inputs = {
        'Resultado.score_100': round(random.uniform(30, 100), 1),
        'Resultado.temps_mis': round(random.uniform(45.0, 180.0), 1),
        'campagne_detail.temps_suspect': random.choice([True, False] + [False] * 8), # 10% de chance de triche
        'Resultado.details_categories': {
            'Phishing': {'score': round(random.uniform(20, 100), 1)},
            'IA Générative': {'score': round(random.uniform(20, 100), 1)},
            'Protection des données': {'score': round(random.uniform(20, 100), 1)}
        }
    }

    # 3. EXÉCUTION DU VRAI MOTEUR ML
    # Le modèle traite les données brutes et ressort les variables exactes demandées par Hafsa
    packaged_data = SimulationInputData(mock_ouiame_inputs, mock_aicha_inputs)
    calculated_metrics = model_cyber.evaluer_employe(packaged_data)

    # 4. Création du profil unique et intelligent dans l'ORM Django
    EmployeeRiskProfile.objects.create(
        user_uuid=uuid.uuid4(),
        department=f["department"],
        
        # Remplissage via les calculs croisés du modèle (Sorties Hafsa)
        honeytoken_score=calculated_metrics['honeytoken_score'],
        ai_score=calculated_metrics['ai_score'],
        azk_score=calculated_metrics['azk_score'],
        global_score=calculated_metrics['global_score'],
        risk_label=calculated_metrics['risk_label'],
        
        # Métriques prédictives et psychologiques issues des formules mathématiques
        profiling_label=calculated_metrics['profiling_secure'],
        predict_prob=calculated_metrics['predict_probability_future_incident'],
        recommendation=f"Département {f['department']} : Appliquer la politique de remédiation adaptative."
    )

    print(f"OK -> {f['full_name']} [{f['department']}] | "
          f"Score Global: {calculated_metrics['global_score']} | "
          f"Label: {calculated_metrics['risk_label']} | "
          f"Profil: {calculated_metrics['profiling_secure']}")

print(f"\n=== FIN : {len(employees_data)} employés injectés et analysés scientifiquement ! ===")