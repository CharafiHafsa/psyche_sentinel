import math

# =====================================================================
#  1. ENCAPSULATION ET NORMALISATION DES DONNÉES D'ENTRÉE
# =====================================================================

class SimulationInputData:
    """
    Conteneur regroupant l'ensemble des variables d'entrée fournies par 
    Ouiame (Comportement pratique) et Aïcha (Connaissances NIST).
    """
    def __init__(self, ouiame_data: dict, aicha_data: dict):
        # --- Variables de Ouiame (Simulation terrain) ---
        self.department = ouiame_data.get('employee.department', 'Inconnu')
        self.action_taken = ouiame_data.get('ScenarioResponse.action_taken', 'ignore')
        self.risk_result = ouiame_data.get('ScenarioResponse.risk_result', 'safe')
        self.time_taken = ouiame_data.get('ScenarioResponse.time_taken', 45.0)
        
        # Statistiques cumulées de la campagne de simulation
        self.total_count = ouiame_data.get('CampaignEmployeeResult.total_count', 1)
        self.safe_count = ouiame_data.get('CampaignEmployeeResult.safe_count', 1)
        self.warning_count = ouiame_data.get('CampaignEmployeeResult.warning_count', 0)
        self.risk_count = ouiame_data.get('CampaignEmployeeResult.risk_count', 0)
        
        # Détails par type d'attaque simulée
        self.categories_ouiame = ouiame_data.get('categories_detail', [])

        # --- Variables de Aïcha (Quiz théorique NIST) ---
        self.quiz_score_100 = aicha_data.get('Resultado.score_100', 100.0)
        self.temps_mis_quiz = aicha_data.get('Resultado.temps_mis', 120.0)
        self.temps_suspect = aicha_data.get('campagne_detail.temps_suspect', False)
        
        # Structure de scores par compétences NIST
        self.details_categories_aicha = aicha_data.get('Resultado.details_categories', {})


# =====================================================================
#  2. MOTEUR DE SCORING CYBER-COMPORTEMENTAL
# =====================================================================

class PsycheSentinelEngine:
    """
    Moteur analytique qui traite les profils individuels (Hafsa variables)
    et génère les indicateurs prédictifs et psychologiques.
    """

    @staticmethod
    def calculer_scores_axes(data: SimulationInputData) -> dict:
        """
        Calcule les scores de vulnérabilité spécifiques aux trois axes exigés.
        Fusionne l'exercice pratique (Ouiame) et les faiblesses théoriques (Aïcha).
        """
        honeytoken_base = 0.0
        ai_base = 0.0
        azk_base = 0.0
        
        # 1. Analyse des scores sur le terrain (Ouiame)
        for cat in data.categories_ouiame:
            stype = cat.get('scenario_type', '')
            score_val = float(cat.get('score', 0.0))
            
            if stype in ['document', 'sharing', 'password']:
                honeytoken_base += score_val
            elif stype in ['ai_leak', 'internal_chat']:
                ai_base += score_val
            elif stype == 'phishing':
                azk_base += score_val
                
        # Normalisation des sous-catégories
        honeytoken_base = honeytoken_base / 3.0 if honeytoken_base > 0 else 0.0
        ai_base = ai_base / 2.0 if ai_base > 0 else 0.0

        # 2. Corrélation avec le manque de connaissances NIST (Aïcha)
        # Niveau de risque théorique = (100 - Score obtenu)
        quiz_honey_risk = 100.0 - float(data.details_categories_aicha.get('Protection des données', {}).get('score', 100.0))
        quiz_ai_risk = 100.0 - float(data.details_categories_aicha.get('IA Générative', {}).get('score', 100.0))
        quiz_azk_risk = 100.0 - float(data.details_categories_aicha.get('Phishing', {}).get('score', 100.0))

        # 3. Pondération finale : 60% Comportement direct / 40% Théorie
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
        Définit le profil psychologique de l'utilisateur face au risque cyber
        en croisant sa vigilance et son niveau de connaissances.
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
        Modélisation statistique via une fonction Logistique (Sigmoïde).
        Calcule la probabilité qu'un utilisateur déclenche un incident cyber.
        """
        beta_0 = -2.5  # Constante/Biais de base
        beta_global = 0.04
        beta_triche = 1.5
        beta_vitesse = -0.02  # Un temps de réponse trop court augmente l'impulsivité

        # Calcul de la combinaison linéaire z
        z = (beta_0 + 
             (beta_global * global_score) + 
             (beta_triche * (1.0 if data.temps_suspect else 0.0)) + 
             (beta_vitesse * data.time_taken))

        # Application de la Sigmoïde
        try:
            probabilite = 1.0 / (1.0 + math.exp(-z))
        except OverflowError:
            probabilite = 1.0 if z > 0 else 0.0

        return round(probabilite * 100, 2)

    def evaluer_employe(self, data: SimulationInputData) -> dict:
        """
        Fonction maîtresse qui orchestre l'évaluation complète d'un profil.
        Retourne les 5 variables requises par Hafsa pour l'agent.
        """
        # Calcul des scores d'axes croisés
        axes = self.calculer_scores_axes(data)
        
        # Calcul du score global (Synthèse des erreurs commises et du quiz)
        comportement_risk = (data.risk_count / data.total_count) * 100 if data.total_count > 0 else 0
        global_score = (0.6 * comportement_risk) + (0.4 * (100.0 - data.quiz_score_100))
        global_score = round(max(0.0, min(100.0, global_score)), 2)

        # Classification du label de risque
        if global_score < 25.0:
            risk_label = "LOW"
        elif global_score < 50.0:
            risk_label = "MEDIUM"
        elif global_score < 75.0:
            risk_label = "HIGH"
        else:
            risk_label = "CRITICAL"

        # Compilation des résultats structurés
        return {
            'honeytoken_score': axes['honeytoken_score'],
            'ai_score': axes['ai_score'],
            'azk_score': axes['azk_score'],
            'global_score': global_score,
            'risk_label': risk_label,
            'profiling_secure': self.determiner_profil_psychologique(data),
            'predict_probability_future_incident': self.predire_probabilite_incident(data, global_score)
        }