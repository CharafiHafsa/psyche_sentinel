#!/usr/bin/env python3
"""
PSYCHE SENTINEL — import_quiz.py
=====================================
Script d'importation du CSV de 200 questions dans PostgreSQL.

Usage :
    python import_quiz.py --csv quiz_v4_100tous_100it.csv [--reset] [--dry-run]

Options :
    --csv     Chemin vers le fichier CSV (requis)
    --reset   Supprime toutes les questions existantes avant import
    --dry-run Affiche les statistiques sans écrire en base

Colonnes CSV attendues :
    Categorie, Question, Difficulte, Poids, Choix_A, Choix_B, Choix_C,
    Reponse_Correcte, Public

Place ce fichier à la racine du projet Django (même niveau que manage.py).
"""

import argparse
import csv
import os
import sys

# ── Bootstrap Django ──────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cognisec.settings')

import django
django.setup()
# ─────────────────────────────────────────────────────────────

from training.models import Question

# ── Mapping colonnes CSV → champs Django ──────────────────────
COLUMN_MAP = {
    'Categorie':        'categorie',
    'Question':         'texte',
    'Difficulte':       'difficulte',
    'Poids':            'poids',
    'Choix_A':          'choix_a',
    'Choix_B':          'choix_b',
    'Choix_C':          'choix_c',
    'Reponse_Correcte': 'reponse_correcte',
    'Public':           'public',
}

# Valeurs valides
VALID_DIFFICULTE = {1, 2, 3}
VALID_POIDS      = set(range(1, 6))
VALID_REPONSES   = {'A', 'B', 'C'}
VALID_PUBLIC     = {Question.Public.TOUS, Question.Public.IT_UNIQUEMENT}

# ─────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description='Importer les questions quiz dans PostgreSQL')
    parser.add_argument('--csv',     required=True, help='Chemin du fichier CSV')
    parser.add_argument('--reset',   action='store_true', help='Supprimer les questions existantes')
    parser.add_argument('--dry-run', action='store_true', help='Simulation sans écriture en base')
    return parser.parse_args()


def valider_ligne(row: dict, num_ligne: int) -> tuple[dict | None, list[str]]:
    """Valide et nettoie une ligne CSV. Retourne (data, erreurs)."""
    errors = []

    try:
        difficulte = int(row.get('Difficulte', '').strip())
        if difficulte not in VALID_DIFFICULTE:
            errors.append(f"Difficulte invalide : {difficulte}")
    except ValueError:
        errors.append("Difficulte non numérique")
        difficulte = 2  # Valeur par défaut

    try:
        poids = int(row.get('Poids', '').strip())
        if poids not in VALID_POIDS:
            errors.append(f"Poids invalide : {poids}")
    except ValueError:
        errors.append("Poids non numérique")
        poids = 3

    reponse = row.get('Reponse_Correcte', '').strip().upper()
    if reponse not in VALID_REPONSES:
        errors.append(f"Reponse_Correcte invalide : '{reponse}'")

    public = row.get('Public', 'Tous').strip()
    if public not in VALID_PUBLIC:
        # Tente de normaliser
        if 'IT' in public.upper():
            public = Question.Public.IT_UNIQUEMENT
        else:
            public = Question.Public.TOUS

    texte = row.get('Question', '').strip()
    if len(texte) < 10:
        errors.append(f"Question trop courte ({len(texte)} chars)")

    for choix in ['Choix_A', 'Choix_B', 'Choix_C']:
        if not row.get(choix, '').strip():
            errors.append(f"{choix} vide")

    if errors:
        return None, errors

    return {
        'categorie':        row.get('Categorie', '').strip(),
        'texte':            texte,
        'choix_a':          row.get('Choix_A', '').strip(),
        'choix_b':          row.get('Choix_B', '').strip(),
        'choix_c':          row.get('Choix_C', '').strip(),
        'reponse_correcte': reponse,
        'difficulte':       difficulte,
        'poids':            poids,
        'public':           public,
    }, []


def afficher_rapport(compteurs: dict, erreurs_lignes: list):
    """Affiche un rapport détaillé de l'import."""
    print("\n" + "═" * 60)
    print("  RAPPORT D'IMPORTATION — PSYCHE SENTINEL")
    print("═" * 60)
    print(f"  ✓ Créées      : {compteurs['crees']:>4}")
    print(f"  ↺ Mises à jour: {compteurs['mises_a_jour']:>4}")
    print(f"  ✗ Erreurs     : {compteurs['erreurs']:>4}")
    print(f"  ─ Ignorées    : {compteurs['ignorees']:>4}")
    print(f"  Σ Total lignes: {compteurs['total']:>4}")
    print("─" * 60)

    # Répartition par catégorie
    if compteurs.get('par_categorie'):
        print("\n  Répartition par catégorie :")
        for cat, n in sorted(compteurs['par_categorie'].items()):
            bar = '█' * min(n, 20)
            print(f"    {cat[:35]:<35} {n:>3}  {bar}")

    # Répartition Public
    if compteurs.get('par_public'):
        print("\n  Répartition Public :")
        for pub, n in compteurs['par_public'].items():
            print(f"    {pub:<25} : {n}")

    # Répartition Difficulté
    if compteurs.get('par_diff'):
        print("\n  Répartition Difficulté :")
        labels = {1: 'Facile', 2: 'Moyen', 3: 'Difficile'}
        for d, n in sorted(compteurs['par_diff'].items()):
            print(f"    Niv.{d} ({labels[d]:<10}) : {n}")

    if erreurs_lignes:
        print(f"\n  ⚠  {len(erreurs_lignes)} lignes avec erreurs :")
        for num, errs in erreurs_lignes[:10]:
            print(f"    Ligne {num:>4} : {', '.join(errs)}")
        if len(erreurs_lignes) > 10:
            print(f"    ... et {len(erreurs_lignes) - 10} autres erreurs")

    print("═" * 60)


def importer(csv_path: str, reset: bool = False, dry_run: bool = False):
    """Fonction principale d'importation."""

    if not os.path.exists(csv_path):
        print(f"✗ Fichier introuvable : {csv_path}")
        sys.exit(1)

    if reset and not dry_run:
        nb_suppr = Question.objects.count()
        Question.objects.all().delete()
        print(f"⚠  {nb_suppr} questions supprimées (--reset)")

    compteurs = {
        'total': 0,
        'crees': 0,
        'mises_a_jour': 0,
        'erreurs': 0,
        'ignorees': 0,
        'par_categorie': {},
        'par_public': {Question.Public.TOUS: 0, Question.Public.IT_UNIQUEMENT: 0},
        'par_diff': {1: 0, 2: 0, 3: 0},
    }
    erreurs_lignes = []
    a_creer        = []

    print(f"\n📂 Lecture de : {csv_path}")
    print("─" * 60)

    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        # Vérifier les colonnes
        colonnes = set(reader.fieldnames or [])
        attendues = set(COLUMN_MAP.keys())
        manquantes = attendues - colonnes
        if manquantes:
            print(f"✗ Colonnes manquantes dans le CSV : {manquantes}")
            print(f"  Colonnes trouvées : {colonnes}")
            sys.exit(1)

        for num_ligne, row in enumerate(reader, start=2):
            compteurs['total'] += 1

            data, errors = valider_ligne(row, num_ligne)

            if errors:
                compteurs['erreurs'] += 1
                erreurs_lignes.append((num_ligne, errors))
                continue

            # Stats
            compteurs['par_categorie'][data['categorie']] = (
                compteurs['par_categorie'].get(data['categorie'], 0) + 1
            )
            compteurs['par_public'][data['public']] = (
                compteurs['par_public'].get(data['public'], 0) + 1
            )
            compteurs['par_diff'][data['difficulte']] = (
                compteurs['par_diff'].get(data['difficulte'], 0) + 1
            )

            if dry_run:
                compteurs['crees'] += 1
                continue

            # Upsert : identifiant unique = (texte, categorie)
            obj, created = Question.objects.update_or_create(
                texte=data['texte'],
                categorie=data['categorie'],
                defaults={
                    'choix_a':          data['choix_a'],
                    'choix_b':          data['choix_b'],
                    'choix_c':          data['choix_c'],
                    'reponse_correcte': data['reponse_correcte'],
                    'difficulte':       data['difficulte'],
                    'poids':            data['poids'],
                    'public':           data['public'],
                }
            )

            if created:
                compteurs['crees'] += 1
            else:
                compteurs['mises_a_jour'] += 1

            # Feedback en direct tous les 20 records
            done = compteurs['crees'] + compteurs['mises_a_jour']
            if done % 20 == 0:
                print(f"  → {done} questions traitées…", end='\r')

    mode = "[DRY-RUN] " if dry_run else ""
    print(f"\n{mode}Import terminé.")
    afficher_rapport(compteurs, erreurs_lignes)

    if not dry_run:
        total_en_base = Question.objects.count()
        print(f"\n  📊 Total en base PostgreSQL : {total_en_base} questions")


# ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    args = parse_args()
    importer(
        csv_path=args.csv,
        reset=args.reset,
        dry_run=getattr(args, 'dry_run', False),
    )
