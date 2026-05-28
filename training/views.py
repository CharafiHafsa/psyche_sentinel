"""
PSYCHE SENTINEL — training/views.py  (Version Complète)
=========================================================
Toutes les fonctionnalités du module de sensibilisation :
  1. Gestion campagnes        (liste, créer, modifier, détail, terminer)
  2. Quiz employé             (accès, soumission, résultat détaillé)
  3. Aperçu admin             (passage_quiz)
  4. Notifications email      (invitations + rappels en threading)
  7. Dashboard statistiques   (ML features, dataviz)
  8. HRN auto                 (mise à jour Employee après quiz)
  9. API JSON                 (stats live)

Conforme NIST SP 800-50 / SP 800-53 / SP 800-63B
"""

import json
import csv
import io
import random
import threading
import logging
import datetime
from datetime import timedelta
from io import BytesIO

from django.utils.dateparse import parse_datetime
from .forms import QuestionForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt 


from core.models import Employee
from .models import Campagne, Question, Resultat

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# ── 0. UTILITAIRES INTERNES ──
# ══════════════════════════════════════════════════════════════

def _selectionner_questions(campagne, public_profil: str):
    """Sélectionne aléatoirement les questions selon les quotas et le profil technique."""
    questions_finales = []
    pool_questions = Question.objects.filter(public=public_profil)
    
    # Tirage Aléatoire sécurisé par Niveau
    q_niv1 = list(pool_questions.filter(difficulte=1))
    questions_finales.extend(random.sample(q_niv1, min(len(q_niv1), campagne.nb_niv1)))
    
    q_niv2 = list(pool_questions.filter(difficulte=2))
    questions_finales.extend(random.sample(q_niv2, min(len(q_niv2), campagne.nb_niv2)))
    
    q_niv3 = list(pool_questions.filter(difficulte=3))
    questions_finales.extend(random.sample(q_niv3, min(len(q_niv3), campagne.nb_niv3)))
    
    return questions_finales

def _calculer_score(questions, reponses):
    """
    Score pondéré NIST adapté anti-pénalité de temps :
    - Cas 1 : Si aucune réponse, score = 0% basé sur le pool total.
    - Cas 2 : Si réponses partielles, calcul basé UNIQUEMENT sur les questions traitées.
    """
    points_max    = 0
    points_gagnes = 0
    nb_correctes  = 0
    details_categories = {}
    reponses_detail = []

    # 🎯 1. Filtriw les questions li fihom chi jawb (Cas 2)
    # On considère une question traitée si la clé existe dans reponses et n'est pas vide
    questions_traitees = [
        q for q in questions 
        if str(q.id) in reponses and reponses[str(q.id)].strip()
    ]

    # 🎯 Cas 1 : Si l'employé n'a répondu à ABSOLUMENT RIEN du tout (reponses vide ou temps expiré direct)
    if not questions_traitees:
        # On calcule le points_max global sur toutes les questions pour le reflet statistique
        for q in questions:
            poids_question = q.poids * q.difficulte
            points_max += poids_question
            
            cat = q.categorie
            if cat not in details_categories:
                details_categories[cat] = {'correct': 0, 'total': 0, 'points': 0, 'points_max': 0}
            details_categories[cat]['total'] += 1
            details_categories[cat]['points_max'] += poids_question
            
            reponses_detail.append({
                'question_id': q.id,
                'choisie': '',
                'correcte': q.reponse_correcte.strip().upper(),
                'est_correcte': False,
                'points': 0,
                'points_max': poids_question,
                'categorie': cat
            })
        
        return {
            'score_100': 0.0,
            'points_gagnes': 0,
            'points_max': points_max,
            'nb_correctes': 0,
            'details_categories': details_categories,
            'reponses_detail': reponses_detail,
        }

   
    for q in questions_traitees:
        # NIST Formula: Poids x Difficulté
        poids_question = q.poids * q.difficulte
        
        lettre_choisie = reponses.get(str(q.id), '').strip().upper()
        jawwab_s7i7    = q.reponse_correcte.strip().upper()
        
        est_correcte   = (lettre_choisie == jawwab_s7i7)
        points_obtenus = poids_question if est_correcte else 0

        # points_max kay-7seb dynamic ghir 3la chno t-jawb
        points_max    += poids_question
        points_gagnes += points_obtenus
        if est_correcte:
            nb_correctes += 1

        # Organisation par catégorie
        cat = q.categorie
        if cat not in details_categories:
            details_categories[cat] = {'correct': 0, 'total': 0, 'points': 0, 'points_max': 0}
        
        details_categories[cat]['total']      += 1
        details_categories[cat]['points_max'] += poids_question
        if est_correcte:
            details_categories[cat]['correct'] += 1
            details_categories[cat]['points']  += points_obtenus

        reponses_detail.append({
            'question_id': q.id,
            'choisie': lettre_choisie,
            'correcte': jawwab_s7i7,
            'est_correcte': est_correcte,
            'points': points_obtenus,
            'points_max': poids_question,
            'categorie': cat
        })

    # Score final sur 100 calculé dynamiquement sur la base des questions traitées
    score_100 = round((points_gagnes / points_max * 100), 2) if points_max > 0 else 0.0
    
    return {
        'score_100': score_100,
        'points_gagnes': points_gagnes,
        'points_max': points_max,
        'nb_correctes': nb_correctes,
        'details_categories': details_categories,
        'reponses_detail': reponses_detail,
    }

@require_POST
def quiz_soumettre(request, campagne_id):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Payload JSON invalide'}, status=400)

    email = data.get('email') or request.session.get('quiz_email')
    reponses = data.get('reponses', {})
    temps_sec = int(data.get('temps_secondes', 0))
    
    # Récupération de la durée prévue (pour sécurité)
    duree_prevue = request.session.get('quiz_duree_totale', 0)

    try:
        campagne = get_object_or_404(Campagne, pk=campagne_id)
        question_ids = list(reponses.keys())
        questions = list(Question.objects.filter(id__in=question_ids))

        # 1. Calcul complet du score via la formule NIST
        score_data = _calculer_score(questions, reponses)

        # 2. Récupération des détails de l'employé (Nom complet et Département)
        employe_nom = email  # Valeur par défaut si l'employé n'est pas trouvé
        division_employe = ""
        try:
            emp = Employee.objects.get(email=email)
            # Gestion du nom complet (ou concaténation prénom + nom selon ton modèle Employee)
            if hasattr(emp, 'full_name') and emp.full_name:
                employe_nom = emp.full_name
            elif hasattr(emp, 'first_name') and hasattr(emp, 'last_name') and (emp.first_name or emp.last_name):
                employe_nom = f"{emp.first_name} {emp.last_name}".strip()
            
            # Récupération du département/division
            if hasattr(emp, 'department') and emp.department:
                division_employe = emp.department
        except Employee.DoesNotExist:
            logger.warning("Employee introuvable lors de la soumission : %s", email)

        # 3. Sauvegarde complète dans la base de données
        resultat, created = Resultat.objects.update_or_create(
            campagne=campagne,
            employe_email=email,
            defaults={
                'employe_nom': employe_nom,               # Fixe l'affichage du Nom & Prénom
                'division': division_employe,             # Fixe la division manquante (remplace "—")
                'score_100': score_data['score_100'],
                'points_gagnes': score_data['points_gagnes'],
                'points_max': score_data['points_max'],
                'nb_correctes': score_data['nb_correctes'],     # Fixe le compteur de réponses correctes (remplace 0/10)
                'nb_total_posees': len(questions),
                'reussi': score_data['score_100'] >= 70,
                'temps_mis': temps_sec,
                'details_categories': score_data['details_categories'],
                'reponses_detail': score_data['reponses_detail'],
                'date_passage': timezone.now(),
            }
        )
        
        # Mettre à jour le score de risque (HRN) automatiquement
        _mettre_a_jour_hrn(email, score_data['score_100'], campagne.nom)
        
        # Nettoyage session
        if 'quiz_duree_totale' in request.session:
            del request.session['quiz_duree_totale']

        return JsonResponse({
            'success': True,
            'score': score_data['score_100'],
            'redirect_url': reverse('quiz_merci')
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
        
def _mettre_a_jour_hrn(employe_email: str, score: float, campagne_nom: str):
    """
    Met à jour le score HRN (Human Risk Score) dans Employee.
    Appelé automatiquement après chaque soumission de quiz.
    Statuts : score < 50 → Alert | 50-70 → Watch | >= 70 → Clear
    """
    try:
        emp = Employee.objects.get(email=employe_email)
        if score < 50:
            emp.status = 'Alert'
        elif score < 70:
            emp.status = 'Watch'
        else:
            emp.status = 'Clear'
        emp.drill_progress = min(100, (emp.drill_progress or 0) + 10)
        emp.last_event     = f"Quiz '{campagne_nom}' — {score:.1f}%"
        emp.save(update_fields=['status', 'drill_progress', 'last_event'])
        logger.info("HRN mis à jour : %s → %s (%.1f%%)", employe_email, emp.status, score)
    except Employee.DoesNotExist:
        logger.warning("Employee introuvable pour HRN : %s", employe_email)
    except Exception as e:
        logger.error("Erreur HRN %s : %s", employe_email, e)


def _envoyer_emails_thread(emails_data: list, subject: str,
                           html_template: str, context_base: dict):
    """
    Envoi massif d'emails en arrière-plan via threading.
    Non-bloquant : la vue répond immédiatement.
    emails_data : [{'email': str, 'nom': str, 'lien': str}, ...]

    Prérequis dans settings.py :
        EMAIL_BACKEND   = 'django.core.mail.backends.smtp.EmailBackend'
        EMAIL_HOST      = 'smtp.gmail.com'
        EMAIL_PORT      = 587
        EMAIL_USE_TLS   = True
        EMAIL_HOST_USER = 'votre@gmail.com'
        EMAIL_HOST_PASSWORD = 'votre_app_password_gmail'
        DEFAULT_FROM_EMAIL  = 'Psyche Sentinel <votre@gmail.com>'
    """
    from django.conf import settings
    import traceback

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) \
                 or getattr(settings, 'EMAIL_HOST_USER', 'noreply@psychesentinel.com')

    def _worker():
        connection = get_connection()
        try:
            connection.open()
            for item in emails_data:
                try:
                    ctx       = {**context_base, **item}
                    # Fallback si template HTML introuvable : email texte seul
                    try:
                        html_body = render_to_string(html_template, ctx)
                    except Exception:
                        html_body = None

                    text_body = (
                        f"Bonjour {item.get('nom', '')},\n\n"
                        f"Vous êtes invité(e) à passer le quiz de sensibilisation "
                        f"cybersécurité « {context_base.get('campagne', '')} ».\n\n"
                        f"Votre lien personnel (valable une seule fois) :\n{item['lien']}\n\n"
                        f"Durée : {context_base.get('duree_minutes', 30)} minutes — "
                        f"{context_base.get('total_questions', '?')} questions\n\n"
                        "Psyche Sentinel — Sensibilisation Cybersécurité NIST SP 800-50"
                    )
                    msg = EmailMultiAlternatives(
                        subject=subject,
                        body=text_body,
                        from_email=from_email,   # ── FIX : explicite, plus None
                        to=[item['email']],
                        connection=connection,
                    )
                    if html_body:
                        msg.attach_alternative(html_body, 'text/html')
                    msg.send()
                    logger.info("✅ Email envoyé → %s", item['email'])
                except Exception as e:
                    logger.error("❌ Erreur email → %s : %s\n%s",
                                 item['email'], e, traceback.format_exc())
        except Exception as e:
            logger.error("❌ Erreur connexion SMTP : %s\n%s", e, traceback.format_exc())
        finally:
            try:
                connection.close()
            except Exception:
                pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t


def _get_mention(score: float) -> str:
    if score >= 90: return 'Avec Félicitations'
    if score >= 80: return 'Très Bien'
    if score >= 70: return 'Bien'
    return ''


# ══════════════════════════════════════════════════════════════
# ── 1. INTERFACE QUIZ EMPLOYÉ ──
# ══════════════════════════════════════════════════════════════

def quiz_acces(request, token: str):
    """
    Point d'entrée public. URL : /training/quiz/<token>/
    Token = email encodé en base64 URL-safe.
    """
    import base64
    try:
        padding       = '=' * (4 - len(token) % 4)
        employe_email = base64.urlsafe_b64decode(token + padding).decode('utf-8')
    except Exception:
        employe_email = token

    campagnes_actives = [
        c for c in Campagne.objects.filter(
            statut__in=[Campagne.Statut.PLANIFIEE, Campagne.Statut.ACTIVE]
        ) if c.est_active
    ]
    if not campagnes_actives:
        return render(request, 'training/quiz_indisponible.html',
                      {'message': 'Aucune campagne active pour le moment.'})

    campagne = campagnes_actives[0]

    email_clean = employe_email.strip().lower()

    a_deja_passe = Resultat.objects.filter(
        campagne=campagne, 
        employe_email__iexact=email_clean
    ).exists()

    if a_deja_passe:
        return render(request, 'training/quiz_deja_passe.html', {'campagne': campagne})

    sess_key = f'quiz_{campagne.id}_{employe_email}'
    if sess_key not in request.session:
        try:
            employe = Employee.objects.get(email=employe_email)
            dept_employe = employe.department or ""
        except Employee.DoesNotExist:
            dept_employe = ""

        public_autorise = (
            "IT uniquement"
            if "IT" in dept_employe.upper()
            else "Tous"
        )

        questions = _selectionner_questions(
            campagne,
            public_profil=public_autorise
        )
        request.session[sess_key] = {
            'ids':        [q.id for q in questions],
            'start_time': timezone.now().isoformat(),
        }
        request.session['quiz_email']       = employe_email
        request.session['quiz_campagne_id'] = campagne.id

    sess          = request.session[sess_key]
    questions_ids = sess['ids']
    questions     = list(Question.objects.filter(id__in=questions_ids))
    order_map     = {qid: i for i, qid in enumerate(questions_ids)}
    questions.sort(key=lambda q: order_map[q.id])

    questions_json = json.dumps([
        {
            'id': q.id, 'categorie': q.categorie, 'texte': q.texte,
            'choix_a': q.choix_a, 'choix_b': q.choix_b, 'choix_c': q.choix_c,
            'difficulte': q.difficulte, 'poids': q.poids, 'public': q.public,
        }
        for q in questions
    ], ensure_ascii=False)

    return render(request, 'training/quiz_interface.html', {
        'campagne':       campagne,
        'questions':      questions,
        'questions_json': questions_json,
        'total':          len(questions),
        'duree_secondes': campagne.duree_minutes * 60,
        'employe_email':  employe_email,
        'mode_apercu':    False,
    })


# ══════════════════════════════════════════════════════════════
# ── 2. GESTION CAMPAGNES (Admin) ──
# ══════════════════════════════════════════════════════════════

@login_required
def campagnes_liste(request):
    """Liste des campagnes avec KPIs agrégés et mise à jour automatique des statuts."""

    campagnes_list = Campagne.objects.exclude(
        statut__in=[Campagne.Statut.TERMINEE, Campagne.Statut.ANNULEE]
    )
    
    for c in campagnes_list:
        c.update_statut()

    # 2. Récupération des données avec annotation
    # On utilise la même classe Manager pour s'assurer d'avoir les données à jour
    campagnes = Campagne.objects.annotate(
        nb_passages=Count('resultats'),
        score_moyen=Avg('resultats__score_100'),
    ).order_by('-date_lancement')

    return render(request, 'training/campagnes_liste.html', {
        'campagnes':       campagnes,
        'total_campagnes': campagnes.count(),
        # Utilise .filter(statut=...) après l'annotation pour refléter les changements
        'actives':         campagnes.filter(statut=Campagne.Statut.ACTIVE).count(),
        'planifiees':      campagnes.filter(statut=Campagne.Statut.PLANIFIEE).count(),
        'total_passages':  Resultat.objects.count(),
    })

def _get_dispo_questions(divisions=None) -> dict:
    """Retourne le nombre de questions disponibles (filtré par division si fourni)."""
    dispo = {}
    for niv in [1, 2, 3]:
        queryset = Question.objects.filter(difficulte=niv)
        
        # Si des divisions sont fournies, on filtre (adapter selon ton modèle)
        if divisions:
            # Ex: si ton modèle Question a un champ 'departement_cible'
            queryset = queryset.filter(departement_cible__in=divisions)
            
        dispo[niv] = queryset.count()
    return dispo

@login_required
def campagne_creer(request):
    """Création d'une nouvelle campagne avec validation automatique (max 25 questions)."""
    divisions = list(
        Employee.objects
        .exclude(department__isnull=True).exclude(department='')
        .values_list('department', flat=True)
        .distinct().order_by('department')
    )

    if request.method == 'POST':
        divisions_cibles = request.POST.getlist('divisions_cibles')

        if not divisions_cibles:
            return render(request, 'training/campagne_form.html', {
                'divisions': divisions,
                'dispo': _get_dispo_questions(),
                'error': "⚠️ Vous devez sélectionner au moins une division cible."
            })
        # 1. Recuperation des champs
        nb_niv1 = int(request.POST.get('nb_niv1', 4))
        nb_niv2 = int(request.POST.get('nb_niv2', 4))
        nb_niv3 = int(request.POST.get('nb_niv3', 2))
        nom     = request.POST.get('nom', '').strip()
        date_lancement = request.POST.get('date_lancement', '')

        # 2.  VERROU DE SÉCURITÉ : Total max 25
        total_questions = nb_niv1 + nb_niv2 + nb_niv3
        if total_questions > 25:
            return render(request, 'training/campagne_form.html', {
                'divisions': divisions, 'dispo': _get_dispo_questions(),
                'error': f"🛑 Action impossible : Le total ({total_questions}) dépasse la limite autorisée de 25 questions.",
            })

        # 3. Validations de base
        if not nom or not date_lancement:
            return render(request, 'training/campagne_form.html', {
                'divisions': divisions, 'dispo': _get_dispo_questions(),
                'error': 'Nom et date de lancement sont obligatoires.',
            })

        date_obj = parse_datetime(date_lancement)
        if not date_obj:
            return render(request, 'training/campagne_form.html', {
                'divisions': divisions, 'dispo': _get_dispo_questions(),
                'error': 'Format de date invalide.',
            })

        # 4. Vérification disponibilité (Global)
        dispo = _get_dispo_questions()
        errs  = []
        for niv, quota in [(1, nb_niv1), (2, nb_niv2), (3, nb_niv3)]:
            if dispo[niv] < quota:
                errs.append(f"Niveau {niv} : {dispo[niv]} dispo (demandé {quota})")
        if errs:
            # 💡 CETTE PARTIE DOIT ÊTRE DÉCALÉE VERS LA DROITE
            return render(request, 'training/campagne_form.html', {
                'divisions': divisions, 
                'dispo': dispo, 
                'error': ' | '.join(errs),
            })

        # 5.  CALCUL DYNAMIQUE (Niveau 1=45s, 2=90s, 3=180s)
        #  CES LIGNES DOIVENT ÊTRE AU MÊME NIVEAU QUE LE 'if'
        duree_totale_sec = (nb_niv1 * 45) + (nb_niv2 * 90) + (nb_niv3 * 180)
        duree_minutes_calc = max(1, round(duree_totale_sec / 60))

        # 6. Création avec la durée calculée
        campagne = Campagne.objects.create(
            nom=nom,
            description=request.POST.get('description', '').strip(),
            divisions_cibles=divisions_cibles,
            date_lancement=date_obj,
            duree_minutes=duree_minutes_calc, # <--- Utilisation du calcul
            nb_niv1=nb_niv1, nb_niv2=nb_niv2, nb_niv3=nb_niv3,
            statut=Campagne.Statut.PLANIFIEE,
        )
        messages.success(request, f'Campagne « {campagne.nom} » créée avec succès.')
        return redirect('campagne_detail', pk=campagne.pk)

    return render(request, 'training/campagne_form.html', {
        'divisions': divisions, 'dispo': _get_dispo_questions(),
    })


@login_required
def campagne_modifier(request, pk: int):
    campagne = get_object_or_404(Campagne, pk=pk)

    if campagne.statut in (Campagne.Statut.TERMINEE, Campagne.Statut.ANNULEE):
        messages.error(request, 'Impossible de modifier une campagne terminée ou annulée.')
        return redirect('campagne_detail', pk=pk)

    divisions = list(
        Employee.objects
        .exclude(department__isnull=True).exclude(department='')
        .values_list('department', flat=True)
        .distinct().order_by('department')
    )

    if request.method == 'POST':
        # 1. Récupération des nouveaux quotas
        nb_niv1 = int(request.POST.get('nb_niv1', campagne.nb_niv1))
        nb_niv2 = int(request.POST.get('nb_niv2', campagne.nb_niv2))
        nb_niv3 = int(request.POST.get('nb_niv3', campagne.nb_niv3))
        divisions_cibles = request.POST.getlist('divisions_cibles')

        # 2. Vérification disponibilité (Appel sans argument puisque ta fonction est globale)
        dispo = _get_dispo_questions()
        errs  = []
        for niv, quota in [(1, nb_niv1), (2, nb_niv2), (3, nb_niv3)]:
            if dispo[niv] < quota:
                errs.append(f"Niv.{niv} : {dispo[niv]} dispo (demandé {quota})")
        
        if errs:
            return render(request, 'training/campagne_form.html', {
                'campagne': campagne, 'divisions': divisions,
                'dispo': dispo, 'edit_mode': True,
                'error': ' | '.join(errs),
            })

        # 3. Calcul dynamique de la durée (pour cohérence avec la création)
        duree_totale_sec = (nb_niv1 * 45) + (nb_niv2 * 90) + (nb_niv3 * 180)
        duree_minutes_calc = max(1, round(duree_totale_sec / 60))

        # 4. Mise à jour des champs
        campagne.nom              = request.POST.get('nom', campagne.nom).strip()
        campagne.description      = request.POST.get('description', '').strip()
        campagne.divisions_cibles = divisions_cibles
        campagne.duree_minutes    = duree_minutes_calc
        campagne.nb_niv1          = nb_niv1
        campagne.nb_niv2          = nb_niv2
        campagne.nb_niv3          = nb_niv3

        date_str = request.POST.get('date_lancement', '')
        if date_str:
            date_obj = parse_datetime(date_str)
            if date_obj:
                campagne.date_lancement = date_obj

        campagne.save()
        messages.success(request, f'Campagne « {campagne.nom} » mise à jour avec succès.')
        return redirect('campagne_detail', pk=pk)

    return render(request, 'training/campagne_form.html', {
        'campagne':  campagne,
        'divisions': divisions,
        'dispo': _get_dispo_questions(),
        'edit_mode': True,
    })

@login_required
def campagne_detail(request, pk: int):
    """
    Détail d'une campagne — version enrichie NIST SP 800-50.
    Affiche : KPIs complets, analyse par catégorie, HRN, alertes temps suspect.
    """
    # ── 1. Campagne + mise à jour statut ─────────────────────────────────
    campagne = get_object_or_404(Campagne, pk=pk)
    campagne.update_statut()
 
    # ── 2. Résultats existants ────────────────────────────────────────────
    resultats_db = campagne.resultats.order_by('-date_passage')
 
    # ── 3. Statistiques globales ──────────────────────────────────────────
    stats = resultats_db.aggregate(
        score_moyen=Avg('score_100'),
        total=Count('id'),
        reussis=Count('id', filter=Q(reussi=True)),
        temps_moyen=Avg('temps_mis'),
    )
 
    nb_passes  = stats['total'] or 0
    nb_reussis = stats['reussis'] or 0
 
    taux_reussite = (
        round((nb_reussis / nb_passes) * 100, 1) if nb_passes > 0 else 0
    )
 
    # ── 4. Employés ciblés / non passés ──────────────────────────────────
    emails_passes = set(resultats_db.values_list('employe_email', flat=True))
 
    if campagne.divisions_cibles:
        employes_cibles = Employee.objects.filter(department__in=campagne.divisions_cibles)
    else:
        employes_cibles = Employee.objects.all()
 
    total_cibles = employes_cibles.count()
    non_passes   = employes_cibles.exclude(email__in=emails_passes)
 
    taux_participation = round((nb_passes / total_cibles * 100), 1) if total_cibles > 0 else 0.0
    nb_vulnerables     = nb_passes - nb_reussis
    taux_vulnerabilite = round((nb_vulnerables / nb_passes * 100), 1) if nb_passes > 0 else 0.0
 
    # ── 5. HRN breakdown (Clear / Watch / Alert) ──────────────────────────
    hrn_clear = sum(1 for r in resultats_db if r.score_100 >= 70)
    hrn_watch = sum(1 for r in resultats_db if 50 <= r.score_100 < 70)
    hrn_alert = sum(1 for r in resultats_db if r.score_100 < 50)
 
    # ── 6. KPIs enrichis ─────────────────────────────────────────────────
    temps_moyen_sec = stats['temps_moyen'] or 0
    temps_moyen_min = int(temps_moyen_sec // 60)
    temps_moyen_s   = int(temps_moyen_sec % 60)
 
    kpis_detail = {
        'participation':    taux_participation,
        'total_cibles':     total_cibles,
        'total_passes':     nb_passes,
        'nb_non_passes':    non_passes.count(),
        'taux_vulnerabilite': taux_vulnerabilite,
        'nb_vulnerables':   nb_vulnerables,
        'temps_moyen_fmt':  f"{temps_moyen_min:02d}:{temps_moyen_s:02d}",
        'hrn_clear':        hrn_clear,
        'hrn_watch':        hrn_watch,
        'hrn_alert':        hrn_alert,
        # Score moyen arrondi pour affichage
        'score_moyen':      round(stats['score_moyen'] or 0, 1),
        # Structure quiz
        'nb_niv1':          campagne.nb_niv1,
        'nb_niv2':          campagne.nb_niv2,
        'nb_niv3':          campagne.nb_niv3,
    }
 
    # ── 7. Analyse par catégorie ──────────────────────────────────────────
    cat_stats: dict = {}
    for r in resultats_db:
        if r.details_categories:
            for cat, data in r.details_categories.items():
                if cat not in cat_stats:
                    cat_stats[cat] = {'correct': 0, 'total': 0, 'points': 0, 'points_max': 0}
                cat_stats[cat]['correct']    += data.get('correct', 0)
                cat_stats[cat]['total']      += data.get('total', 0)
                cat_stats[cat]['points']     += data.get('points', 0)
                cat_stats[cat]['points_max'] += data.get('points_max', 0)
 
    categories_data = [
        {
            'categorie':  cat,
            'taux':       round((d['correct'] / d['total']) * 100, 1) if d['total'] > 0 else 0,
            'correct':    d['correct'],
            'total':      d['total'],
            'points':     d['points'],
            'points_max': d['points_max'],
            'is_critique': (round((d['correct'] / d['total']) * 100, 1) if d['total'] > 0 else 0) < 50,
        }
        for cat, d in cat_stats.items()
    ]
    categories_data.sort(key=lambda x: x['taux'])  # critiques en premier
 
    # Catégorie la plus faible (pour colonne "Catég. critique" dans le tableau employé)
    categorie_critique_globale = categories_data[0]['categorie'] if categories_data else None
 
    # ── 8. Pool mixé : passés + non passés, enrichi ───────────────────────
    resultats_finaux = []
 
    for r in resultats_db:
        # Catégorie critique individuelle (la catégorie avec le plus bas taux pour cet employé)
        cat_individuelle = None
        if r.details_categories:
            cat_taux = [
                (cat, round((d['correct'] / d['total']) * 100, 1) if d['total'] > 0 else 0)
                for cat, d in r.details_categories.items()
            ]
            if cat_taux:
                cat_taux.sort(key=lambda x: x[1])
                cat_individuelle = cat_taux[0][0] if cat_taux[0][1] < 70 else None
 
        # Statut HRN individuel
        if r.score_100 >= 70:
            hrn_statut = 'clear'
        elif r.score_100 >= 50:
            hrn_statut = 'watch'
        else:
            hrn_statut = 'alert'
 
        # Alerte temps suspect (< 30 secondes pour tout le quiz)
        temps_suspect = r.temps_mis is not None and r.nb_total_posees > 0 and r.temps_mis < 30
 
        resultats_finaux.append({
            'employe_nom':          r.employe_nom or r.employe_email,
            'employe_email':        r.employe_email,
            'division':             r.division or '—',
            'score_100':            r.score_100,
            'points_gagnes':        r.points_gagnes,
            'points_max':           r.points_max,
            'nb_correctes':         r.nb_correctes,
            'nb_total_posees':      r.nb_total_posees,
            'temps_formate':        r.temps_formate,
            'temps_mis':            r.temps_mis or 0,
            'reussi':               r.reussi,
            'date_passage':         r.date_passage,
            'statut_quiz':          'complete',
            'hrn_statut':           hrn_statut,
            'cat_critique':         cat_individuelle,
            'temps_suspect':        temps_suspect,
            'resultat_id':          r.id,
            'details_categories_json': json.dumps(r.details_categories or {}),  # ← AJOUTER
        })
 
    for emp in non_passes:
        nom_complet = ''
        if hasattr(emp, 'full_name') and emp.full_name:
            nom_complet = emp.full_name
        elif hasattr(emp, 'first_name') and hasattr(emp, 'last_name') and (emp.first_name or emp.last_name):
            nom_complet = f"{emp.first_name} {emp.last_name}".strip()
        if not nom_complet:
            nom_complet = emp.email
        is_finished = (campagne.date_fin < timezone.now()) if campagne.date_fin else False
        resultats_finaux.append({
            'employe_nom':     nom_complet,
            'employe_email':   emp.email,
            'division':        emp.department or '—',
            'score_100':       None,
            'points_gagnes':   None,
            'points_max':      None,
            'nb_correctes':    0,
            'nb_total_posees': 0,
            'temps_formate':   '—',
            'temps_mis':       0,
            'reussi':          False,
            'date_passage':    None,
            'statut_quiz':     'non_commence',
            'campagne_terminee': is_finished,
            'hrn_statut':      None,
            'cat_critique':    None,
            'temps_suspect':   False,
            'resultat_id':     None,
        })
 
    # ── 9. Alertes temps suspect (pour bannière dédiée) ───────────────────
    alerte_temps = [r for r in resultats_finaux if r['temps_suspect']]
 
    # ── 10. Alertes NIST
    employes_alerte = [r for r in resultats_finaux if r['hrn_statut'] in ['alert', 'watch']]
    alert_count = len(employes_alerte)

    # ── 11. Rendu ─────────────────────────────────────────────────────────
    return render(request, 'training/campagne_detail.html', {
        'campagne':         campagne,
        'resultats':        resultats_finaux,
        'stats':            stats,
        'taux_reussite':    taux_reussite,
        'nb_non_passes':    non_passes.count(),
        'categories_data':  categories_data,
        'kpis_detail':      kpis_detail,
        'alerte_temps':     alerte_temps,
        'alert_count':      alert_count,
        'cat_critique_globale': categorie_critique_globale,
    })

@login_required
def campagne_terminer(request, pk: int):
    campagne = get_object_or_404(Campagne, pk=pk)
    campagne.statut = Campagne.Statut.TERMINEE
    campagne.save(update_fields=['statut'])
    messages.success(request, f'Campagne « {campagne.nom} » terminée.')
    return redirect('campagne_detail', pk=pk)

@login_required
def passage_quiz(request, campagne_id):
    """
    Distribution intelligente avec accès prioritaire pour les administrateurs.
    """
    campagne = get_object_or_404(Campagne, id=campagne_id)
    
    # 1. Verification de l'accès (Admin ou Employé ciblé)
    est_admin = request.user.is_staff
    
    try:
        dept_employe = request.user.employee.department  
    except AttributeError:
        dept_employe = ""

    divisions_selectionnees = campagne.divisions_cibles or []
    est_cibled = "Tout" in divisions_selectionnees or dept_employe in divisions_selectionnees
    
    # Condition : Soit c'est un admin, soit l'employé fait partie des cibles
    if est_admin or est_cibled:
        
        # 🎯 LOGIQUE DYNAMIQUE : On considère le profil IT si admin, sinon selon département
        public_autorise = "IT uniquement" if (est_admin or "IT" in str(dept_employe).upper()) else "Tous"

        questions = _selectionner_questions(campagne, public_profil=public_autorise)
        
        # 3. CALCUL DYNAMIQUE DU TEMPS
        temps_par_niveau = {1: 45, 2: 90, 3: 180}
        duree_totale_secondes = sum(temps_par_niveau.get(q.difficulte, 60) for q in questions)
        
        request.session['quiz_duree_totale'] = duree_totale_secondes
        request.session['quiz_start_time'] = timezone.now().isoformat()

        questions_json = json.dumps([
            {
                'id': q.id, 'texte': q.texte, 'categorie': q.categorie,
                'choix_a': q.choix_a, 'choix_b': q.choix_b, 'choix_c': q.choix_c,
                'difficulte': q.difficulte
            }
            for q in questions
        ], ensure_ascii=False)
        
        return render(request, 'training/quiz_interface.html', {
            'campagne': campagne, 
            'questions': questions, 
            'questions_json': questions_json,
            'total': len(questions), 
            'duree_secondes': duree_totale_secondes, 
            'employe_email': request.user.email,
            'mode_apercu': False,
        })
    else:
        return render(request, 'training/quiz_indisponible.html', {
            'message': "Votre département n'est pas ciblé par cette campagne."
        })
# ══════════════════════════════════════════════════════════════
# ── 4. NOTIFICATIONS EMAIL ──
# ══════════════════════════════════════════════════════════════

@login_required
@require_POST
def envoyer_invitations_campagne(request, pk: int):
    """
    Envoi d'invitations à TOUS les employés des divisions cibles
    qui n'ont pas encore passé le quiz.
    Token base64 URL-safe unique par employé — envoi non-bloquant (threading).
    """
    import base64

    campagne = get_object_or_404(Campagne, pk=pk)
    mode     = request.POST.get('mode', 'invitation')

    # ── Filtre selon les divisions choisies dans la campagne ──────────
    if campagne.divisions_cibles and not any(x.upper() in ['TOUT', 'ALL', 'ANY'] for x in campagne.divisions_cibles if isinstance(x, str)):

        employes = Employee.objects.filter(
            department__in=campagne.divisions_cibles
        ).exclude(email='').exclude(email__isnull=True)
    else:
        # Aucune division spécifiée → tous les employés actifs
        employes = Employee.objects.exclude(email='').exclude(email__isnull=True)

    # Exclure uniquement ceux qui ont déjà passé cette campagne
    emails_passes   = set(campagne.resultats.values_list('employe_email', flat=True))
    employes_cibles = employes.exclude(email__in=emails_passes)

    if not employes_cibles.exists():
        messages.warning(
            request,
            'Tous les employés des divisions cibles ont déjà passé cette campagne.'
        )
        return redirect('campagne_detail', pk=pk)

    base_url    = request.build_absolute_uri('/')[:-1]
    emails_data = []
    for emp in employes_cibles:
        # Token = email encodé base64 URL-safe (décodé dans quiz_acces)
        token = base64.urlsafe_b64encode(
            emp.email.encode('utf-8')
        ).decode('ascii').rstrip('=')
        lien = f"{base_url}{reverse('quiz_acces', args=[token])}"
        emails_data.append({
            'email': emp.email,
            'nom':   getattr(emp, 'full_name', None) or emp.email,
            'lien':  lien,
        })

    if mode == 'rappel':
        subject  = f'[Rappel] Quiz cybersécurité — {campagne.nom}'
        template = 'training/email_rappel.html'
    else:
        subject  = f'[Psyche Sentinel] Quiz de sensibilisation — {campagne.nom}'
        template = 'training/email_invitation.html'

    # 1. On prépare le contexte global pour le template d'email
    context_base = {
        'campagne': campagne.nom,
        'duree_minutes': campagne.duree_minutes,
        'total_questions': campagne.total_questions,
    }
    _envoyer_emails_thread(emails_data, subject, template, context_base)

    messages.success(request, f"Invitations envoyées à {len(emails_data)} employés.")
    return redirect('campagne_detail', pk=pk)


# ══════════════════════════════════════════════════════════════
# ── 7. BANQUE DE QUESTIONS ──
# ══════════════════════════════════════════════════════════════

@login_required
@user_passes_test(lambda u: u.is_staff)
def banque_questions(request):
    categorie  = request.GET.get('categorie', '')
    difficulte = request.GET.get('difficulte', '')
    public     = request.GET.get('public', '')
    search     = request.GET.get('q', '')

    qs = Question.objects.all()
    if categorie:  qs = qs.filter(categorie=categorie)
    if difficulte: qs = qs.filter(difficulte=difficulte)
    if public:     qs = qs.filter(public=public)
    if search:     qs = qs.filter(texte__icontains=search)

    categories = (
        Question.objects
        .values_list('categorie', flat=True)
        .distinct().order_by('categorie')
    )

    return render(request, 'training/banque_questions.html', {
        'questions':  qs.order_by('categorie', 'difficulte')[:200],
        'categories': categories,
        'total_tous': Question.objects.filter(public=Question.Public.TOUS).count(),
        'total_it':   Question.objects.filter(
            public=Question.Public.IT_UNIQUEMENT
        ).count(),
        'total':      Question.objects.count(),
        'filtres': {
            'categorie': categorie, 'difficulte': difficulte,
            'public': public, 'q': search,
        },
    })

@login_required
def import_questions(request):
    if request.method == 'POST' and request.FILES.get('fichier_csv'):
        csv_file = request.FILES['fichier_csv']
        
        # 1. Verification dyal l-extension
        if not csv_file.name.endswith('.csv'):
            messages.error(request, "Erreur: Veuillez fournir un fichier CSV.")
            return redirect('banque_questions')

        try:
            data_set = csv_file.read().decode('UTF-8')
            io_string = io.StringIO(data_set)
            reader = csv.reader(io_string, delimiter=',', quotechar='"')
            
            next(reader) # Ngzou s-star l-owl (Header: texte,categorie,difficulte,poids,public,reponse)

            for row in reader:
                if len(row) >= 6:
                    Question.objects.create(
                        texte=row[0],
                        categorie=row[1],
                        difficulte=int(row[2]),
                        poids=int(row[3]),
                        public=row[4],
                        reponse_correcte=row[5]
                    )
            messages.success(request, "Importation réussie !")
        except Exception as e:
            messages.error(request, f"Erreur lors de l'importation: {e}")
            
    return redirect('banque_questions')


# ══════════════════════════════════════════════════════════════
# ── 8. API JSON ──
# ══════════════════════════════════════════════════════════════

@login_required
def api_stats_live(request):
    """
    Stats temps réel pour polling (toutes les 30s) 
    filtrées UNIQUEMENT par la campagne active.
    """
  
    campagne_active = Campagne.objects.filter(statut=Campagne.Statut.ACTIVE).first()
    if not campagne_active:
        campagne_active = Campagne.objects.order_by('-date_lancement').first()
        

    if not campagne_active:
        return JsonResponse({
            'participation': 0,
            'score_moyen': 0,
            'vulnerabilite': 0,
            'total_passes': 0,
            'total_cibles': 0
        })
        
    
    resultats = Resultat.objects.filter(campagne=campagne_active)
    nb_passes = resultats.count()
    

    from core.models import Employee
    if campagne_active.divisions_cibles:
        total_cibles = Employee.objects.filter(department__in=campagne_active.divisions_cibles).count()
    else:
        total_cibles = Employee.objects.count()
        
    # 4. Calculer les métriques d'impact cyber
    taux_participation = round((nb_passes / total_cibles * 100), 1) if total_cibles > 0 else 0.0
    
    kpis = resultats.aggregate(
        score_moyen=Avg('score_100'),
        reussis=Count('id', filter=Q(reussi=True)),
    )
    
    score_moyen = kpis['score_moyen'] or 0.0
    nb_reussis = kpis['reussis'] or 0
    
    # 🚨 Taux de vulnérabilité humains (Ceux sous le seuil NIST de 70%)
    nb_vulnerables = nb_passes - nb_reussis
    taux_vulnerabilite = round((nb_vulnerables / nb_passes * 100), 1) if nb_passes > 0 else 0.0
    
    # 5. Renvoyer les données exactes 
    return JsonResponse({
        'participation': taux_participation,
        'score_moyen':   round(score_moyen, 1),
        'vulnerabilite': taux_vulnerabilite,
        'total_passes':   nb_passes,
        'total_cibles':   total_cibles,
    })

def quiz_merci(request):
    return render(request, 'training/quiz_merci.html')


@login_required
def campagne_delete(request, pk):
    campagne = get_object_or_404(Campagne, pk=pk)
    if request.method == 'POST':
        campagne.delete()
        return redirect('campagnes_liste') # Rjje3ha l-liste nishan
    
    # Ila chi wa7ed bgha i-dkhel nishan b URL, rjje3o l-liste hitach l-m-si7 khasso POST
    return redirect('campagnes_liste')


# ══════════════════════════════════════════════════════════════
# ── 9. API STATISTIQUES AVANCÉES — /api/stats/departements/ ──
# ══════════════════════════════════════════════════════════════

from django.db.models.functions import TruncMonth

@login_required
def api_stats_departements(request):
    from collections import defaultdict

    tous_resultats = list(
        Resultat.objects
        .exclude(division='')
        .values('division', 'date_passage', 'score_100', 'reussi', 'details_categories')
        .order_by('date_passage')
    )

    # ── 1. Évolution du RISQUE par département (100 - score) ────
    dept_points = defaultdict(list)
    for r in tous_resultats:
        risque = round(100 - (r['score_100'] or 0), 1)
        dept_points[r['division']].append({
            'date':  r['date_passage'].strftime('%d/%m %H:%M'),
            'score': risque,   # ← c'est le RISQUE maintenant
        })

    evolution_dept = [
        {'departement': dept, 'points': points}
        for dept, points in dept_points.items()
    ]

    # ── 2. Stats par département ─────────────────────────────────
    dept_stats = defaultdict(lambda: {'risques': [], 'echecs': 0, 'total': 0})
    for r in tous_resultats:
        d = r['division']
        risque = round(100 - (r['score_100'] or 0), 1)
        dept_stats[d]['risques'].append(risque)
        dept_stats[d]['total'] += 1
        if not r['reussi']:
            dept_stats[d]['echecs'] += 1

    stats_dept = []
    for dept, s in dept_stats.items():
        risque_moyen = round(sum(s['risques']) / len(s['risques']), 1) if s['risques'] else 0
        taux_echec   = round((s['echecs'] / s['total']) * 100, 1) if s['total'] > 0 else 0
        stats_dept.append({
            'departement': dept,
            'risque':      risque_moyen,   # ← RISQUE (pas score)
            'taux_echec':  taux_echec,
            'passages':    s['total'],
        })

    # ── 3. Top 5 risqués = risque moyen le plus ÉLEVÉ ───────────
    top_risques = sorted(
        stats_dept,
        key=lambda x: x['risque'],
        reverse=True   # le plus risqué (risque le plus haut) en premier
    )[:5]

    # ── 4. Heatmap dept × catégorie (% RISQUE par catégorie) ────
    import json
    heatmap_raw = defaultdict(lambda: defaultdict(lambda: {'correct': 0, 'total': 0}))

    for r in tous_resultats:
        if not r['details_categories']:
            continue
        details = r['details_categories']
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except Exception:
                continue
        for cat, data in details.items():
            total_cat   = data.get('total', 0)
            correct_cat = data.get('correct', 0)
            if total_cat > 0:
                heatmap_raw[r['division']][cat]['correct'] += correct_cat
                heatmap_raw[r['division']][cat]['total']   += total_cat

    # Cellule = RISQUE (100 - % correctes)
    heatmap = {}
    for dept, cats in heatmap_raw.items():
        heatmap[dept] = {}
        for cat, vals in cats.items():
            if vals['total'] > 0:
                taux_reussite = (vals['correct'] / vals['total']) * 100
                heatmap[dept][cat] = round(100 - taux_reussite, 1)  # ← RISQUE
            else:
                heatmap[dept][cat] = 100  # aucune bonne réponse = risque max

    all_categories = sorted(set(
        cat for cats in heatmap.values() for cat in cats
    ))

    return JsonResponse({
        'stats_dept':      stats_dept,
        'evolution_dept':  evolution_dept,
        'heatmap':         heatmap,
        'categories':      all_categories,
        'top_risques':     top_risques,
    })