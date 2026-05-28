import math
import uuid
from django.db import models

# =====================================================================
#  1. MODÈLE ORM DJANGO (STRUCTURE DE LA BASE DE DONNÉES - HAFSA)
# =====================================================================

class EmployeeRiskProfile(models.Model):
    """
    Modèle unique stockant l'analyse cyber-comportementale finale 
    générée par le moteur ML pour chaque employé.
    """
    user_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    department = models.CharField("Département", max_length=100)
    
    # Les 5 variables individuelles d'Agent (Exigées par Hafsa)
    honeytoken_score = models.FloatField(default=0.0)
    ai_score = models.FloatField(default=0.0)
    azk_score = models.FloatField(default=0.0)
    global_score = models.FloatField(default=0.0)
    risk_label = models.CharField(max_length=20, default="LOW") # LOW, MEDIUM, HIGH, CRITICAL
    
    # Indicateurs avancés (Psychologie & Prédiction)
    profiling_label = models.CharField(max_length=100, default="SECURE")
    predict_prob = models.FloatField(default=0.0) # Probabilité d'incident futur en %
    recommendation = models.TextField(default="")
    
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Profil de Risque Employé"
        verbose_name_plural = "Profils de Risque Employés"

    def __str__(self):
        return f"Profil {self.user_uuid} - {self.department} ({self.risk_label})"


# =====================================================================
#  2. ENCAPSULATION DES ENTRÉES (OUIAME & AÏCHA)
# =====================================================================

class SimulationInputData:
    """
    Conteneur qui normalise et valide les variables issues des simulations 
    pratiques (Ouiame) et des quiz théoriques NIST (Aïcha).
    """
    def __init__(self, ouiame_data: dict, aicha_data: dict):
        # --- Données comportementales (Ouiame) ---
        self.department = ouiame_data.get('employee.department', 'Inconnu')
        self.action_taken = ouiame_data.get('ScenarioResponse.action_taken', 'ignore')
        self.risk_result = ouiame_data.get('ScenarioResponse.risk_result', 'safe')
        self.time_taken = ouiame_data.get('ScenarioResponse.time_taken', 45.0)
        
        # Agrégats des campagnes de simulation
        self.total_count = ouiame_data.get('CampaignEmployeeResult.total_count', 1)
        self.safe_count = ouiame_data.get('CampaignEmployeeResult.safe_count', 1)
        self.warning_count = ouiame_data.get('CampaignEmployeeResult.warning_count', 0)
        self.risk_count = ouiame_data.get('CampaignEmployeeResult.risk_count', 0)
        self.categories_ouiame = ouiame_data.get('categories_detail', [])

        # --- Données théoriques NIST (Aïcha) ---
        self.quiz_score_100 = aicha_data.get('Resultado.score_100', 100.0)
        self.temps_mis_quiz = aicha_data.get('Resultado.temps_mis', 120.0)
        self.temps_suspect = aicha_data.get('campagne_detail.temps_suspect', False)
        self.details_categories_aicha = aicha_data.get('Resultado.details_categories', {})


# =====================================================================
#  3. MOTEUR MATHÉMATIQUE ET COMPORTEMENTAL (LOGIQUE ML)
# =====================================================================

class PsycheSentinelModel:
    """
    Moteur de scoring croisé, de profiling psychologique et de 
    calcul prédictif par fonction logistique.
    """
    
    @staticmethod
    def calculer_scores_axes(data: SimulationInputData) -> dict:
        """
        Calcule les scores de vulnérabilité sur les 3 axes majeurs.
        Fait converger la pratique (Ouiame) et les faiblesses théoriques (Aïcha).
        """
        honeytoken_base = 0.0
        ai_base = 0.0
        azk_base = 0.0
        
        # Extraction depuis les simulations (Ouiame)
        for cat in data.categories_ouiame:
            stype = cat.get('scenario_type', '')
            score_val = float(cat.get('score', 0.0))
            
            if stype in ['document', 'sharing', 'password']:
                honeytoken_base += score_val
            elif stype in ['ai_leak', 'internal_chat']:
                ai_base += score_val
            elif stype == 'phishing':
                azk_base += score_val
                
        # Normalisation des scores pratiques
        honeytoken_base = honeytoken_base / 3.0 if honeytoken_base > 0 else 0.0
        ai_base = ai_base / 2.0 if ai_base > 0 else 0.0

        # Récupération du taux d'erreur théorique (Aïcha) : Risque = 100 - ScoreQuiz
        quiz_honey_risk = 100.0 - float(data.details_categories_aicha.get('Protection des données', {}).get('score', 100.0))
        quiz_ai_risk = 100.0 - float(data.details_categories_aicha.get('IA Générative', {}).get('score', 100.0))
        quiz_azk_risk = 100.0 - float(data.details_categories_aicha.get('Phishing', {}).get('score', 100.0))

        # Pondération finale : 60% Réalité terrain (Pratique) / 40% Maîtrise théorique
        honeytoken_score = (0.6 * honeytoken_base) + (0.4 * quiz_honey_risk)
        ai_score = (0.6 * ai_base) + (0.4 * quiz_ai_risk)
        azk_score = (0.6 * azk_base) + (0.4 * quiz_azk_risk)

        return {
            'honeytoken_score': round(honeytoken_score, 2),
            'ai_score': round(ai_score, 2),
            'azk_score': round(azk_score, 2)
        }

    @staticmethod
    def determiner_profil_psychologique(data: SimulationInputData) -> str:
        """
        Analyse l'écart comportemental pour catégoriser l'état d'esprit de l'employé.
        """
        theorie_ok = data.quiz_score_100 >= 70.0
        pratique_dangereuse = data.risk_count > 0 or data.risk_result == 'risk'

        if theorie_ok and not pratique_dangereuse:
            return "SECURE"
        elif theorie_ok and pratique_dangereuse:
            return "GOOD KNOWLEDGE BUT RISKLY BEHAVIOR"
        elif not theorie_ok and pratique_dangereuse:
            return "UNAWARE AND RISKLY"
        else:
            return "CAREFUL BUT LACKS KNOWLEDGE"

    @staticmethod
    def predire_probabilite_incident(data: SimulationInputData, global_score: float) -> float:
        """
        Calcule mathématiquement le risque de causer un incident futur.
        Utilise une fonction Sigmoïde basée sur les facteurs aggravants (vitesse, triche).
        """
        beta_0 = -2.5  # Seuil de base
        beta_global_score = 0.04
        beta_temps_suspect = 1.5
        beta_vitesse_reaction = -0.02

        # Calcul du score linéaire combiné (z)
        z = (beta_0 + 
             (beta_global_score * global_score) + 
             (beta_temps_suspect * (1.0 if data.temps_suspect else 0.0)) + 
             (beta_vitesse_reaction * data.time_taken))

        # Application de la formule Sigmoïde
        try:
            probabilite = 1.0 / (1.0 + math.exp(-z))
        except OverflowError:
            probabilite = 1.0 if z > 0 else 0.0

        return round(probabilite * 100, 2)

    def evaluer_employe(self, data: SimulationInputData) -> dict:
        """
        Fonction centrale appelée par le script send-data.py.
        Retourne le dictionnaire complet avec les métriques attendues.
        """
        axes = self.calculer_scores_axes(data)
        
        # Calcul du score global
        comportement_risk_score = (data.risk_count / data.total_count) * 100 if data.total_count > 0 else 0
        global_score = (0.6 * comportement_risk_score) + (0.4 * (100.0 - data.quiz_score_100))
        global_score = round(max(0.0, min(100.0, global_score)), 2)

        # Détermination du label de sévérité
        if global_score < 25.0:
            risk_label = "LOW"
        elif global_score < 50.0:
            risk_label = "MEDIUM"
        elif global_score < 75.0:
            risk_label = "HIGH"
        else:
            risk_label = "CRITICAL"

        return {
            'honeytoken_score': axes['honeytoken_score'],
            'ai_score': axes['ai_score'],
            'azk_score': axes['azk_score'],
            'global_score': global_score,
            'risk_label': risk_label,
            'profiling_secure': self.determiner_profil_psychologique(data),
            'predict_probability_future_incident': self.predire_probabilite_incident(data, global_score)
        }