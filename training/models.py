"""
PSYCHE SENTINEL — training/models.py
=====================================
Modèles de données du module de sensibilisation.
Auteur : Psyche Sentinel Dev Team
Conforme NIST SP 800-50 / SP 800-53
"""

from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import timedelta

# ─────────────────────────────────────────────
# 1. QUESTION
# ─────────────────────────────────────────────

class Question(models.Model):
    """
    Banque de questions QCM NIST.
    Importée depuis le CSV via import_quiz.py.
    """

    class Difficulte(models.IntegerChoices):
        FACILE   = 1, 'Facile'
        MOYEN    = 2, 'Moyen'
        DIFFICILE = 3, 'Difficile'

    class Public(models.TextChoices):
        TOUS        = 'Tous',        'Tous les départements'
        IT_UNIQUEMENT = 'IT uniquement', 'Division IT uniquement'

    # ── Contenu ──
    categorie        = models.CharField(max_length=100, db_index=True)
    texte            = models.TextField(verbose_name="Énoncé de la question")
    choix_a          = models.TextField(verbose_name="Choix A")
    choix_b          = models.TextField(verbose_name="Choix B")
    choix_c          = models.TextField(verbose_name="Choix C")
    reponse_correcte = models.CharField(
        max_length=1,
        choices=[('A', 'A'), ('B', 'B'), ('C', 'C')],
        verbose_name="Réponse correcte"
    )

    # ── Scoring NIST ──
    difficulte = models.IntegerField(
        choices=Difficulte.choices,
        default=Difficulte.MOYEN,
        validators=[MinValueValidator(1), MaxValueValidator(3)]
    )
    poids = models.IntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Poids de la question (1–5). Utilisé dans le calcul du score pondéré."
    )

    # ── Ciblage ──
    public = models.CharField(
        max_length=20,
        choices=Public.choices,
        default=Public.TOUS,
        db_index=True
    )

    # ── Meta ──
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Question"
        verbose_name_plural = "Questions"
        ordering            = ['categorie', 'difficulte']
        indexes             = [
            models.Index(fields=['categorie', 'difficulte', 'public']),
        ]

    def __str__(self):
        return f"[{self.categorie}] Niv.{self.difficulte} — {self.texte[:60]}…"

    @property
    def poids_max(self):
        """Points maximum atteignables sur cette question."""
        return self.poids * self.difficulte


# ─────────────────────────────────────────────
# 2. CAMPAGNE
# ─────────────────────────────────────────────

class Campagne(models.Model):
    """
    Campagne de sensibilisation déployée par l'administrateur.
    Définit les quotas par niveau et les divisions LDAP cibles.
    """

    class Statut(models.TextChoices):
        BROUILLON  = 'brouillon',  'Brouillon'
        PLANIFIEE  = 'planifiee',  'Planifiée'
        ACTIVE     = 'active',     'Active'
        TERMINEE   = 'terminee',   'Terminée'
        ANNULEE    = 'annulee',    'Annulée'

    # ── Identification ──
    nom             = models.CharField(max_length=200)
    description     = models.TextField(blank=True)

    # ── Ciblage LDAP ──
    # Stocké en JSON : liste de strings (noms de divisions/OU LDAP)
    # ex: ["Marketing", "Finance", "RH"]
    divisions_cibles = models.JSONField(
        default=list,
        help_text='Liste des divisions LDAP cibles ou ["Tout"] pour cibler tout le monde.'
    )
    

    # ── Planification ──
    date_lancement  = models.DateTimeField(
        help_text="La campagne s'active automatiquement à cette date/heure."
    )
    duree_minutes   = models.PositiveIntegerField(
        default=30,
        help_text="Durée totale accordée à l'employé pour compléter le quiz (en minutes)."
    )
    date_fin = models.DateTimeField(null=True, blank=True, verbose_name="Date de fin réelle")

    # ── Quotas par niveau ──
    nb_niv1 = models.PositiveIntegerField(
        default=4,
        verbose_name="Nb questions Niveau 1 (Facile)"
    )
    nb_niv2 = models.PositiveIntegerField(
        default=4,
        verbose_name="Nb questions Niveau 2 (Moyen)"
    )
    nb_niv3 = models.PositiveIntegerField(
        default=2,
        verbose_name="Nb questions Niveau 3 (Difficile)"
    )

    # ── Statut ──
    statut         = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.BROUILLON,
        db_index=True
    )

    # ── Meta ──
    date_creation  = models.DateTimeField(auto_now_add=True)
    date_maj       = models.DateTimeField(auto_now=True)
    def save(self, *args, **kwargs):
        # 1. Calcul automatique dyal date_fin (Lancement + Duree)
        if self.date_lancement:
            self.date_fin = self.date_lancement + timedelta(minutes=self.duree_minutes)
        
        # 2. Gestion dyal Timezone (dakchi li knti dayra)
        if self.date_lancement and timezone.is_naive(self.date_lancement):
            self.date_lancement = timezone.make_aware(
                self.date_lancement, 
                timezone.get_current_timezone()
            )
            
        super().save(*args, **kwargs)
    class Meta:
        verbose_name        = "Campagne"
        verbose_name_plural = "Campagnes"
        ordering            = ['-date_lancement']

    def __str__(self):
        return f"{self.nom} — {self.get_statut_display()} ({self.date_lancement:%d/%m/%Y})"

    def update_statut(self):
    # On obtient l'heure actuelle, puis on la convertit en heure locale (Casablanca)
        maintenant_utc = timezone.now()
        maintenant_local = timezone.localtime(maintenant_utc)
        
        # Assure-toi que ta date_lancement est aussi comparée en heure locale
        date_lancement_local = timezone.localtime(self.date_lancement)
        
        # Calcul de la fin théorique
        fin_test = date_lancement_local + timedelta(minutes=self.duree_minutes)

        if self.statut == self.Statut.PLANIFIEE and maintenant_local >= date_lancement_local:
            self.statut = self.Statut.ACTIVE
            self.save(update_fields=['statut'])
        
        elif self.statut == self.Statut.ACTIVE and maintenant_local > fin_test:
            self.statut = self.Statut.TERMINEE
            self.save(update_fields=['statut'])
    @property
    def est_active(self):
        """Retourne True si la campagne est réellement en cours."""
        # On force la vérification du statut actuel avant de répondre
        self.update_statut()
        return self.statut == self.Statut.ACTIVE

    @property
    def total_questions(self):
        return self.nb_niv1 + self.nb_niv2 + self.nb_niv3

    def get_statut_badge_class(self):
        """Retourne la classe CSS badge correspondant au statut."""
        mapping = {
            'brouillon': 'badge-neutral',
            'planifiee':  'badge-info',
            'active':     'badge-success',
            'terminee':   'badge-violet',
            'annulee':    'badge-danger',
        }
        return mapping.get(self.statut, 'badge-neutral')


# ─────────────────────────────────────────────
# 3. RÉSULTAT
# ─────────────────────────────────────────────

class Resultat(models.Model):
    """
    Enregistrement du passage d'un employé à une campagne.
    Score pondéré sur 100 selon la formule NIST.
    """

    # ── Liens ──
    campagne      = models.ForeignKey(
        Campagne,
        on_delete=models.CASCADE,
        related_name='resultats'
    )

    # ── Employé (lié à core.Employee via email) ──
    employe_email = models.EmailField(db_index=True)
    employe_nom   = models.CharField(max_length=255, blank=True)
    division      = models.CharField(max_length=150, blank=True, db_index=True)

    # ── Scoring ──
    score_100         = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Score pondéré sur 100 : (ΣPoints gagnés / ΣPoints max) × 100"
    )
    points_gagnes     = models.FloatField(default=0)
    points_max        = models.FloatField(default=0)
    nb_correctes      = models.PositiveIntegerField(default=0)
    nb_total_posees   = models.PositiveIntegerField(default=0)

    # ── Détails par catégorie (JSON) ──
    # ex: {"Phishing & Email": {"correct": 3, "total": 4}, ...}
    details_categories = models.JSONField(default=dict, blank=True)

    # ── Temps ──
    temps_mis     = models.PositiveIntegerField(
        help_text="Temps effectif en secondes",
        default=0
    )
    date_passage  = models.DateTimeField(default=timezone.now, db_index=True)

    # ── Statut de réussite ──
    reussi        = models.BooleanField(default=False)
    seuil_reussite = models.FloatField(
        default=70.0,
        help_text="Seuil de réussite en % (défaut 70)"
    )

    # ── Réponses détaillées (JSON) ──
    # ex: [{"question_id": 1, "choisie": "B", "correcte": "B", "points": 6}, ...]
    reponses_detail = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name        = "Résultat"
        verbose_name_plural = "Résultats"
        ordering            = ['-date_passage']
        unique_together     = [('campagne', 'employe_email')]

    def __str__(self):
        return (
            f"{self.employe_email} — {self.campagne.nom} "
            f"| Score : {self.score_100:.1f}% "
            f"({'✓' if self.reussi else '✗'})"
        )

    @property
    def temps_formate(self):
        """Retourne le temps sous forme mm:ss."""
        m, s = divmod(self.temps_mis, 60)
        return f"{m:02d}:{s:02d}"

    @property
    def temps_moyen_par_question(self):
        if self.nb_total_posees == 0:
            return 0
        return round(self.temps_mis / self.nb_total_posees, 1)
