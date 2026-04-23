from django.db import models

# Create your models here.
from django.db import models
from django.utils import timezone
import uuid

# On importe le modèle Employee depuis l'application core
from core.models import Employee

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
    COMMAND_CHOICES = [('PING', 'Check Now'), ('RESTART', 'Redémarrer Agent'), ('CONTAIN', 'Isoler Machine')]
    
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='commands')
    command = models.CharField(max_length=50, choices=COMMAND_CHOICES)
    is_executed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.command} for {self.agent.hostname} (Executed: {self.is_executed})"