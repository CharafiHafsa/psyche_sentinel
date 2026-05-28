"""
PSYCHE SENTINEL — training/admin.py
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import Question, Campagne, Resultat


# ─────────────────────────────────────────────────────────────
# QUESTION
# ─────────────────────────────────────────────────────────────

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display   = ['categorie', 'texte_court', 'difficulte_badge',
                      'poids_display', 'public_badge', 'reponse_correcte']
    list_filter    = ['categorie', 'difficulte', 'public']
    search_fields  = ['texte', 'categorie']
    list_per_page  = 50
    ordering       = ['categorie', 'difficulte']

    def texte_court(self, obj):
        return obj.texte[:75] + '…' if len(obj.texte) > 75 else obj.texte
    texte_court.short_description = 'Question'

    def difficulte_badge(self, obj):
        colors = {1: '#22c55e', 2: '#f59e0b', 3: '#f87171'}
        labels = {1: 'Facile', 2: 'Moyen', 3: 'Difficile'}
        return format_html(
            '<span style="color:{};font-weight:700;">Niv.{} {}</span>',
            colors.get(obj.difficulte, '#fff'), obj.difficulte,
            labels.get(obj.difficulte, '')
        )
    difficulte_badge.short_description = 'Difficulté'

    def poids_display(self, obj):
        filled = '█' * obj.poids
        empty  = '░' * (5 - obj.poids)
        return format_html(
            '<span style="color:var(--violet, #7c3aed);font-family:monospace;">{}{}</span>',
            filled, empty
        )
    poids_display.short_description = 'Poids'

    def public_badge(self, obj):
        if obj.public == Question.Public.IT_UNIQUEMENT:
            return format_html('<span style="color:#06b6d4;font-weight:700;">💻 IT</span>')
        return format_html('<span style="color:#94a3b8;">👥 Tous</span>')
    public_badge.short_description = 'Public'


# ─────────────────────────────────────────────────────────────
# CAMPAGNE
# ─────────────────────────────────────────────────────────────

@admin.register(Campagne)
class CampagneAdmin(admin.ModelAdmin):
    list_display = ['nom', 'statut', 'date_lancement', 'duree_minutes', 'total_questions'] 
    list_filter = ['statut']
    search_fields  = ['nom', 'description']
    readonly_fields = ['date_creation', 'date_maj']
    ordering       = ['-date_lancement']

    fieldsets = (
        ('Identification', {
            'fields': ('nom', 'description')
        }),
        ('Ciblage', {
            'fields': ('divisions_cibles',)
        }),
        ('Planification', {
            'fields': ('date_lancement', 'duree_minutes', 'statut')
        }),
        ('Quotas par niveau', {
            'fields': ('nb_niv1', 'nb_niv2', 'nb_niv3'),
            'description': 'Nombre de questions à tirer par difficulté'
        }),
        ('Méta', {
            'fields': ('date_creation', 'date_maj'),
            'classes': ('collapse',)
        }),
    )

    def statut_badge(self, obj):
        colors = {
            'brouillon': '#64748b',
            'planifiee': '#60a5fa',
            'active':    '#22c55e',
            'terminee':  '#a78bfa',
            'annulee':   '#f87171',
        }
        return format_html(
            '<span style="color:{};font-weight:700;">● {}</span>',
            colors.get(obj.statut, '#fff'),
            obj.get_statut_display()
        )
    statut_badge.short_description = 'Statut'

    def quotas_display(self, obj):
        return f"N1:{obj.nb_niv1} / N2:{obj.nb_niv2} / N3:{obj.nb_niv3} = {obj.total_questions}Q"
    quotas_display.short_description = 'Quotas'

    def nb_resultats(self, obj):
        n = obj.resultats.count()
        return format_html('<span style="font-weight:700;">{}</span>', n)
    nb_resultats.short_description = 'Passages'


# ─────────────────────────────────────────────────────────────
# RÉSULTAT
# ─────────────────────────────────────────────────────────────

@admin.register(Resultat)
class ResultatAdmin(admin.ModelAdmin):
    list_display   = ['employe_email', 'division', 'campagne',
                      'score_badge', 'nb_correctes', 'nb_total_posees',
                      'temps_formate_display', 'date_passage']
    list_filter    = ['reussi', 'campagne', 'division']
    search_fields  = ['employe_email', 'employe_nom']
    ordering       = ['-date_passage']
    readonly_fields = ['score_100', 'points_gagnes', 'points_max',
                       'reponses_detail', 'details_categories',
                       'date_passage', 'reussi']

    def score_badge(self, obj):
        color = '#22c55e' if obj.reussi else '#f87171'
        icon  = '✓' if obj.reussi else '✗'
        return format_html(
            '<span style="color:{};font-weight:700;">{} {:.1f}%</span>',
            color, icon, obj.score_100
        )
    score_badge.short_description = 'Score'

    def temps_formate_display(self, obj):
        return obj.temps_formate
    temps_formate_display.short_description = 'Durée'
