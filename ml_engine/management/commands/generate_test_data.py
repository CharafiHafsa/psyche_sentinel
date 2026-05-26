from django.core.management.base import BaseCommand
from ml_engine.models import EmployeeRiskProfile
import random
import uuid

class Command(BaseCommand):
    help = 'Génère des données fictives pour tester le module ML'

    def handle(self, *args, **kwargs):
        departments = ['RH', 'IT', 'Finance', 'Marketing', 'Sales']
        
        self.stdout.write("Génération des données en cours...")

       
        EmployeeRiskProfile.objects.all().delete()

        for i in range(50):

            if i < 30:
                quiz = random.randint(80, 100)
                phishing = 0
                honey = 0

            elif i < 45:
                quiz = random.randint(40, 70)
                phishing = random.randint(1, 3)
                honey = random.randint(0, 1)

            else:
                quiz = random.randint(0, 30)
                phishing = random.randint(3, 10)
                honey = random.randint(2, 5)

            EmployeeRiskProfile.objects.create(
                user_uuid=uuid.uuid4(),
                department=random.choice(departments),
                quiz_score=quiz,
                phishing_clicks=phishing,
                honeytoken_access=honey,
                nbr_of_tests=random.randint(1, 5)
            )

        self.stdout.write(self.style.SUCCESS('✅ 50 profils générés avec succès'))