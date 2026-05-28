"""
PSYCHE SENTINEL — training/urls.py (Complet)
=============================================
Toutes les routes du module de sensibilisation.

À inclure dans cognisec/urls.py :
    path('training/', include('training.urls')),
"""

from django.urls import path
from . import views

urlpatterns = [

    # ── Quiz Employé (public — base_public.html) ──────────────
    path('quiz/<str:token>/',
         views.quiz_acces,
         name='quiz_acces'),

    # urls.py
    path('quiz/<int:campagne_id>/submit/', 
         views.quiz_soumettre, 
         name='quiz_soumettre'),


     path('merci/',
         views.quiz_merci, 
         name='quiz_merci'), 

    # ── Gestion Campagnes (admin) ──────────────────────────────
    path('campagnes/',
         views.campagnes_liste,
         name='campagnes_liste'),

    path('campagnes/nouvelle/',
         views.campagne_creer,
         name='campagne_creer'),

    path('campagnes/<int:pk>/',
         views.campagne_detail,
         name='campagne_detail'),

    path('campagnes/<int:pk>/modifier/',
         views.campagne_modifier,
         name='campagne_modifier'),

    path('campagnes/<int:pk>/terminer/',
         views.campagne_terminer,
         name='campagne_terminer'),

   
    path('campagnes/<int:campagne_id>/apercu/', 
         views.passage_quiz, 
         name='passage_quiz'),

    # ── Notifications Email ────────────────────────────────────
    path('campagnes/<int:pk>/inviter/',
         views.envoyer_invitations_campagne,
         name='envoyer_invitations'),


    # ── Dashboard & Banque ─────────────────────────────────────
    

    path('api/stats/live/',
         views.api_stats_live,
         name='api_stats_live'),
         
     path('api/stats/departements/',
         views.api_stats_departements,
         name='api_stats_departements'),

    path('questions/',
         views.banque_questions,
         name='banque_questions'),
     
     path('questions/import/', 
         views.import_questions, 
         name='import_questions'),
     
     path('campagnes/', 
         views.campagnes_liste, 
         name='campagnes_liste'),

    path('campagnes/<int:pk>/inviter/', 
         views.envoyer_invitations_campagne, 
         name='envoyer_invitations_campagne'),
    
     path('campagne/<int:pk>/delete/', 
         views.campagne_delete, 
         name='campagne_delete'),
         
    
]