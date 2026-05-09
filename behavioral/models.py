from django.db import models
from django.utils import timezone
import uuid
from core.models import Employee
import string
import random


class Agent(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'En attente d\'installation'),
        ('Online', 'En ligne'),
        ('Offline', 'Hors ligne'),
        ('Compromised', 'Compromis (Alerte)')
    ]

    # Liaison : Un employé peut théoriquement avoir plusieurs machines (ex: Desktop + Laptop)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='agents')
    
    # Identité Système (rempli automatiquement lors de la première connexion de l'agent)
    hostname = models.CharField(max_length=255, blank=True, null=True, help_text="Nom de la machine cible (ex: DESKTOP-X92)")
    ip_address = models.GenericIPAddressField(blank=True, null=True, help_text="Dernière adresse IP connue")
    
    # Sécurité et Authentification (Généré instantanément à la création)
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, help_text="Jeton unique pour l'API REST")
    
    # Télémétrie en temps réel
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Pending')
    last_heartbeat = models.DateTimeField(blank=True, null=True, help_text="Dernier signal de vie reçu de l'agent")
    
    # Métadonnées
    version = models.CharField(max_length=50, default='1.0.0')
    created_at = models.DateTimeField(auto_now_add=True)

    # Sauvegarder le consentement :
    user_consent_granted = models.BooleanField(default=False, help_text="L'employé a-t-il cliqué sur Accepter sur la machine ?")
    user_consent_timestamp = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        machine_name = self.hostname if self.hostname else "Machine Inconnue"
        return f"Agent {machine_name} - {self.employee.full_name}"

    @property
    def is_online_realtime(self):
        """
        Propriété calculée à la volée :
        Si l'agent n'a pas donné signe de vie depuis plus de 5 minutes (300 secondes),
        on le considère hors ligne, même si son statut indique le contraire.
        """
        if not self.last_heartbeat:
            return False
        now = timezone.now()
        diff = now - self.last_heartbeat
        return diff.total_seconds() < 300
    
class DeploymentConsentLog(models.Model):
    """Immutable audit trail proving the admin authorized agent deployment on a specific employee."""
    admin = models.ForeignKey('core.CustomUser', on_delete=models.CASCADE)
    target_employee = models.ForeignKey('core.Employee', on_delete=models.CASCADE)
    agent_token = models.UUIDField(help_text="The token generated during this authorization")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Deployment authorized by {self.admin.email} for {self.target_employee.full_name}"
    
class AgentLog(models.Model):
    """ Vrais logs remontés par l'agent ou générés par le serveur """
    LOG_LEVELS = [('INFO', 'Info'), ('WARNING', 'Warning'), ('ERROR', 'Error'), ('ALERT', 'Alert')]
    
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='logs')
    level = models.CharField(max_length=20, choices=LOG_LEVELS, default='INFO')
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.level}] {self.agent.hostname} - {self.timestamp}"

class AgentCommand(models.Model):
    """ File d'attente des commandes C2 envoyées par l'Admin à l'Agent """
    COMMAND_CHOICES = [
        ('PING', 'Check Now'), 
        ('RESTART', 'Redémarrer Agent'), 
        ('CONTAIN', 'Isoler Machine'),
        ('DEPLOY_HONEYTOKEN', 'Déployer Leurre'),
        ('PAUSE_CAMPAIGN', 'Pause'),
        ('RESUME_CAMPAIGN', 'Reprise'),
        ('CLEANUP_HONEYTOKENS', 'Nettoyer Leurres'),
        ('START_AI_MONITOR', 'Démarrer Surveillance IA'),
        ('STOP_AI_MONITOR', 'Arrêter Surveillance IA')
        ]
    
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='commands')
    command = models.CharField(max_length=50, choices=COMMAND_CHOICES)
    
    payload = models.JSONField(null=True, blank=True)

    is_executed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    execute_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.command} for {self.agent.hostname} (Executed: {self.is_executed})"
    
def generate_campaign_name():
    chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"OP-{chars}"

class SimulationModule(models.Model):
    """ Table dynamique stockant les types de tests disponibles """
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True) # ex: HONEYTOKEN, PHISHING
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default='shield') # Icône Lucide

    def __str__(self):
        return self.name

class TestCampaign(models.Model):
    name = models.CharField(max_length=50, default=generate_campaign_name, unique=True)
    
    # NOUVEAU : Relation ManyToMany pour plusieurs tests à la fois
    modules = models.ManyToManyField(SimulationModule, related_name='campaigns')
    
    target_department = models.CharField(max_length=100, default='ALL') 
    
    # NOUVEAU : Durée unifiée en minutes pour supporter heures/jours/mois
    duration_minutes = models.IntegerField(help_text="Durée totale du test en minutes")
    
    is_scheduled = models.BooleanField(default=False)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    
    status = models.CharField(max_length=20, default='Running')
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_paused_at = models.DateTimeField(null=True, blank=True)
    total_paused_minutes = models.IntegerField(default=0, help_text="Minutes passées en pause")

    def __str__(self):
        return self.name
    

class HoneytokenTemplate(models.Model):
    """ Bibliothèque des faux documents à générer selon le contexte """
    
    # Périmètre
    department = models.CharField(
        max_length=50,
        default='ALL',
        help_text="ex: ALL, HR, IT, FINANCE. Le document ne sera déployé que sur les agents de ce département."
    )

    # Apparence du fichier
    file_name = models.CharField(max_length=100, help_text="ex: 2026_Salaries_Review")
    file_extension = models.CharField(
        max_length=10,
        choices=[
            ('docx', 'Word'),
            ('xlsx', 'Excel'),
            ('pdf', 'PDF'),
            ('txt', 'Text')
        ],
        default='docx'
    )

    # Emplacement cible
    DIRECTORY_CHOICES = [
        ('DESKTOP', 'Bureau (Desktop)'),
        ('DOCUMENTS', 'Documents'),
        ('DOWNLOADS', 'Téléchargements')
    ]
    target_directory = models.CharField(
        max_length=50,
        choices=DIRECTORY_CHOICES,
        default='DESKTOP'
    )

    # Contenu du fichier
    fake_content = models.TextField(
        default="CONFIDENTIAL - Access restricted.\n\nError loading encrypted document."
    )


    # Déclencheur
    trigger_on = models.CharField(
        max_length=50,
        choices=[
            ('OPEN', 'Fichier Ouvert (Accès en lecture)'),
            ('MODIFY', 'Fichier Modifié'),
            ('DELETE', 'Fichier Supprimé')
        ],
        default='OPEN'
    )

    SENSITIVITY_CHOICES = [
        (5, 'Critique (Salaires, Mots de passe, Clés)'),
        (4, 'Sensible Business (Stratégie, Contrats)'),
        (3, 'Opérationnel (Architecture, Risques)'),
        (2, 'Interne (Mémos, Politiques)'),
        (1, 'Faible Valeur (Mots-clés SEO, Logs)')
    ]
    data_sensitivity = models.IntegerField(
        choices=SENSITIVITY_CHOICES, 
        default=3,
        help_text="Valeur de la donnée pour la formule de sévérité"
    )

    weight = models.IntegerField(default=1, help_text="Gravité de l'infraction (ex: 1=Basse, 5=Critique)")
    is_active = models.BooleanField(default=True)
    description = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.file_name}.{self.file_extension} ({self.department})"


class HoneytokenInstance(models.Model):
    """ Historique et état des leurres réellement déployés sur les machines cibles """
    
    # Liaisons (Le Qui, Le Quoi, Le Pourquoi)
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='honeytokens')
    template = models.ForeignKey(HoneytokenTemplate, on_delete=models.CASCADE)
    campaign = models.ForeignKey('TestCampaign', on_delete=models.CASCADE, related_name='honeytoken_instances')

    # Informations de déploiement
    file_path = models.CharField(max_length=255, help_text="Chemin absolu généré sur la machine cible")
    created_at = models.DateTimeField(auto_now_add=True)

    # Statut du piège
    triggered = models.BooleanField(default=False)
    first_triggered_at = models.DateTimeField(null=True, blank=True)
    triggered_at = models.DateTimeField(null=True, blank=True)

    # Stocke la séquence ["OPEN", "MODIFY", "DELETE"]
    action_sequence = models.JSONField(default=list, blank=True) 
    
    # Time Factor (pour le ML plus tard) : temps en secondes
    time_to_trigger_seconds = models.IntegerField(null=True, blank=True)
    
    # Gravité finale calculée (Sensitivity * Max Action Factor)
    highest_severity = models.FloatField(default=0.0)

    def update_severity(self):
        """ Calcule la sévérité basée sur la séquence d'actions """
        if not self.action_sequence:
            return 0.0

        # Dictionnaire des facteurs d'action de vos notes
        action_factors = {
            'OPEN': 1.0,   # Curiosity
            'MODIFY': 1.5, # Interaction
            'DELETE': 2.0  # Intentional cover-up
        }

        # Trouver le facteur maximum parmi les actions effectuées
        factors_used = [action_factors.get(action, 1.0) for action in self.action_sequence]
        max_action_factor = max(factors_used) if factors_used else 1.0

        # Formule : Data Sensitivity x Action Factor
        sensitivity = self.template.data_sensitivity
        self.highest_severity = sensitivity * max_action_factor
        self.save()

    def __str__(self):
        return f"Piège {self.template.file_name} sur {self.agent.hostname} - Sévérité Max: {self.highest_severity}"

class SystemNotification(models.Model):
    """ Stocke les événements majeurs pour la page Notifications """
    TYPES = [('INFO', 'Info'), ('SUCCESS', 'Succès'), ('WARNING', 'Alerte'), ('ERROR', 'Erreur')]
    
    title = models.CharField(max_length=255)
    message = models.TextField()
    type = models.CharField(max_length=20, choices=TYPES, default='INFO')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    link = models.CharField(max_length=255, blank=True, null=True, help_text="URL de redirection optionnelle")

    def __str__(self):
        return f"[{self.type}] {self.title}"
    

# ==========================================
# MODULE 2 : SHADOW AI & DATA LEAKAGE (DLP)
# ==========================================

class AILeakAlert(models.Model):
    """ Enregistre les métadonnées d'une tentative de fuite de données vers une IA """
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='ai_leaks')
    campaign = models.ForeignKey('TestCampaign', on_delete=models.CASCADE, related_name='ai_leak_alerts')
    
    # La plateforme détectée (ex: ChatGPT, Claude, Gemini)
    ai_platform = models.CharField(max_length=100)
    
    # Le type de donnée (Regex matché) : ex: EMAIL_LIST, API_KEY, SOURCE_CODE, HR_DATA
    data_type_detected = models.CharField(max_length=100)
    
    # Métadonnées éthiques (On stocke la taille, mais PAS le texte)
    clipboard_length = models.IntegerField(default=0)
    
    # Contexte comportemental
    action_type = models.CharField(
        max_length=50, 
        choices=[
            ('VISIT', 'Visite simple de la plateforme'),
            ('PASTE', 'Données collées dans la plateforme')
        ],
        default='PASTE'
    )
    
    # Gravité de l'incident (1 à 5) basée sur vos regex
    severity = models.IntegerField(default=1)
    
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Fuite {self.data_type_detected} sur {self.ai_platform} par {self.agent.hostname} (Gravité: {self.severity})"