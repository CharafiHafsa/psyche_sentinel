from django.core.management.base import BaseCommand
from ml_engine.engine import run_risk_analysis

class Command(BaseCommand):
    help = "Lance l'analyse ML sur les profils"

    def handle(self, *args, **kwargs):
        result = run_risk_analysis()
        self.stdout.write(self.style.SUCCESS(result))