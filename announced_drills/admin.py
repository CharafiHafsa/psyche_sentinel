from django.contrib import admin
from .models import Scenario, ScenarioAction, CampaignRun, CampaignScenario, ScenarioResponse

admin.site.register(Scenario)
admin.site.register(ScenarioAction)
admin.site.register(CampaignRun)
admin.site.register(CampaignScenario)
admin.site.register(ScenarioResponse)