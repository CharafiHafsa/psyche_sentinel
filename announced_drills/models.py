from django.db import models

class Scenario(models.Model):
    SCENARIO_TYPES = [
        ('phishing', 'Phishing'),
        ('ai_leak', 'Fuite IA'),
        ('document', 'Document'),
        ('internal_chat', 'Chat interne'),
        ('sharing', 'Partage'),
        ('password', 'Mot de passe'),
    ]

    VARIANT_LEVELS = [
        ('legit', 'Légitime'),
        ('ambiguous', 'Ambigu'),
        ('malicious', 'Malveillant'),
    ]

    RISK_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    UI_MODES = [
        ('email', 'Email'),
        ('ai_prompt', 'Assistant IA'),
        ('file', 'Document'),
        ('chat', 'Message / Support'),
        ('share', 'Partage fichier'),
        ('form', 'Formulaire'),
    ]

    title = models.CharField(max_length=200)

    scenario_type = models.CharField(max_length=30, choices=SCENARIO_TYPES)
    variant_level = models.CharField(max_length=20, choices=VARIANT_LEVELS)
    target_departments = models.JSONField(default=list, blank=True)

    ui_mode = models.CharField(max_length=30, choices=UI_MODES)
    sender_name = models.CharField(max_length=150, blank=True)
    sender_email = models.CharField(max_length=150, blank=True)
    subject = models.CharField(max_length=200, blank=True)
    description = models.TextField()
    

    content_primary = models.TextField()
    content_secondary = models.TextField(blank=True)
    risk_items = models.TextField(blank=True)
    warning_items = models.TextField(blank=True)

    risk_level = models.CharField(max_length=20, choices=RISK_LEVELS, default='medium')
    is_active = models.BooleanField(default=True)


    def __str__(self):
        return f"{self.title} ({self.scenario_type} - {self.variant_level})"

class ScenarioAction(models.Model):
    ACTION_STYLES = [
        ('primary', 'Principal'),
        ('secondary', 'Secondaire'),
        ('ghost', 'Discret'),
    ]

    RISK_RESULTS = [
        ('safe', 'Prudent'),
        ('warning', 'Douteux'),
        ('risk', 'Risqué'),
    ]

    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name='actions')
    label = models.CharField(max_length=100)
    action_value = models.CharField(max_length=100)
    style = models.CharField(max_length=20, choices=ACTION_STYLES, default='secondary')
    risk_result = models.CharField(max_length=20, choices=RISK_RESULTS, default='warning')
    order_index = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.scenario.title} - {self.label}"
class CampaignRun(models.Model):
    campaign_name = models.CharField(max_length=200)
    # target_department = models.CharField(max_length=100, default='all')
    DELIVERY_MODE_CHOICES = [
        ('manual', 'Partage manuel'),
        ('scheduled', 'Envoi programmé'),
    ]

    STATUS_CHOICES = [
        ('ready', 'Prête'),
        ('scheduled', 'Programmée'),
        ('sent', 'Envoyée'),
        ('running', 'En cours'),
        ('expired', 'Expirée'),
        ('completed', 'Terminée'),
    ]

    delivery_mode = models.CharField(
        max_length=20,
        choices=DELIVERY_MODE_CHOICES,
        default='manual'
    )

    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)

    validity_days = models.PositiveIntegerField(default=7)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='ready'
    )
    target_departments = models.JSONField(default=list, blank=True)
    question_count = models.PositiveIntegerField(default=10)
    start_link = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # status = models.CharField(max_length=20, default='created')
    def __str__(self):
        return f"{self.campaign_name} - Run #{self.id}"


class CampaignScenario(models.Model):
    campaign_run = models.ForeignKey(CampaignRun, on_delete=models.CASCADE, related_name='campaign_scenarios')
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE)
    order_index = models.PositiveIntegerField()

    class Meta:
        ordering = ['order_index']

    def __str__(self):
        return f"Run {self.campaign_run.id} - {self.scenario.title} ({self.order_index})"


class ScenarioResponse(models.Model):
    campaign_run = models.ForeignKey(CampaignRun, on_delete=models.CASCADE)
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE)
    action_taken = models.CharField(max_length=100)
    risk_result = models.CharField(max_length=20)
    time_taken = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_text = models.TextField(blank=True)
    attached_file_name = models.CharField(max_length=255, blank=True)
    employee = models.ForeignKey(
        'core.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    def __str__(self):
        return f"Response for run {self.campaign_run.id} / {self.scenario.title}"
    
class CampaignEmployeeResult(models.Model):
    campaign_run = models.ForeignKey(CampaignRun, on_delete=models.CASCADE)
    employee = models.ForeignKey('core.Employee', on_delete=models.CASCADE)

    total_count = models.PositiveIntegerField(default=0)
    safe_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    risk_count = models.PositiveIntegerField(default=0)

    score = models.PositiveIntegerField(default=0)
    status_label = models.CharField(max_length=50, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('campaign_run', 'employee')

    def __str__(self):
        return f"{self.employee} - {self.campaign_run} - {self.score}"
    

class CampaignEmployeeTypeResult(models.Model):

    SCENARIO_TYPE_CHOICES = [
        ('phishing', 'Phishing'),
        ('ai_leak', 'Fuite IA'),
        ('document', 'Document'),
        ('internal_chat', 'Chat interne'),
        ('sharing', 'Partage'),
        ('password', 'Mot de passe'),
    ]

    campaign_run = models.ForeignKey(
        CampaignRun,
        on_delete=models.CASCADE
    )

    employee = models.ForeignKey(
        'core.Employee',
        on_delete=models.CASCADE
    )

    scenario_type = models.CharField(
        max_length=30,
        choices=SCENARIO_TYPE_CHOICES
    )

    total_count = models.PositiveIntegerField(default=0)

    safe_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    risk_count = models.PositiveIntegerField(default=0)

    score = models.PositiveIntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (
            'campaign_run',
            'employee',
            'scenario_type'
        )

    def __str__(self):
        return (
            f"{self.employee} - "
            f"{self.scenario_type} - "
            f"{self.score}"
        )
class ScenarioSensitiveItem(models.Model):
    LEVEL_CHOICES = [
        ('risk', 'Risk'),
        ('warning', 'Warning'),
    ]

    MATCH_TYPE_CHOICES = [
        ('exact', 'Correspondance exacte'),
        ('contains', 'Contient'),
    ]

    scenario = models.ForeignKey(
        Scenario,
        on_delete=models.CASCADE,
        related_name='sensitive_items'
    )
    label = models.CharField(max_length=150)
    value = models.TextField()
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    match_type = models.CharField(max_length=20, choices=MATCH_TYPE_CHOICES, default='exact')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.scenario.title} - {self.label} ({self.level})"