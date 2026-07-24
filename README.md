# Reporting Mensuel

Application locale de reporting comptable : import d'un CSV, validation stricte,
calcul d'indicateurs, détection de variations, synthèse locale ou Gemini, PDF et
comparaison de deux exercices.

## Ce que le projet démontre

- API FastAPI avec interface web responsive, protégée par une clé d'accès locale.
- Validation métier : colonnes attendues, comptes 6/7, montants, totaux et limites de volume.
- File de traitements persistante avec SQLite, reprise des tâches après redémarrage.
- Calcul de KPI et alertes de variation configurables.
- Génération d'un PDF de neuf pages avec graphiques et avertissements de contrôle.
- Historique, téléchargement, suppression et comparaison de deux exercices.
- Tests unitaires, API, PDF et parcours navigateur desktop/mobile.

## Lancer la démonstration

Prérequis : Python 3.12 ou supérieur.

```powershell
.\.venv-reporting\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv-reporting\Scripts\python.exe -m app --demo
```

Ouvrir [http://127.0.0.1:8000](http://127.0.0.1:8000). La clé d'accès est créée
au premier démarrage dans `data/demo/access.key`. Les fichiers fictifs 2024 et
2025 sont téléchargeables depuis l'écran d'import.

Pour utiliser la configuration normale, copier `.env.example` vers `.env`,
renseigner `API_ACCESS_KEY` et, seulement si nécessaire, `GEMINI_API_KEY`, puis lancer :

```powershell
.\.venv-reporting\Scripts\python.exe -m app
```

Ne jamais versionner `.env`, `data/`, `uploads/` ou `reports/` : ils peuvent
contenir des données financières.

## Format CSV

Le séparateur peut être `;`, `,` ou une tabulation. Les colonnes sont :

```text
Compte;Libellé;Nature;Janvier;Février;Mars;Avril;Mai;Juin;Juillet;Août;Septembre;Octobre;Novembre;Décembre;Total
```

`Nature` accepte `Produit` pour un compte commençant par `7` et `Charge` pour un
compte commençant par `6`. Le total doit correspondre à la somme des douze mois.
Une cellule vide est comptée comme zéro et apparaît dans les avertissements du rapport.

## API

L'interface utilise l'API suivante. Les routes métier demandent
`Authorization: Bearer <clé d'accès>`.

| Méthode | Route | Usage |
| --- | --- | --- |
| `POST` | `/upload` | Ajouter un CSV, un exercice et une option IA |
| `GET` | `/status/{id}` | Suivre une génération |
| `GET` | `/reports` | Consulter l'historique |
| `GET` | `/reports/{id}` | Lire les indicateurs et alertes |
| `GET` | `/download/{id}` | Télécharger le PDF |
| `GET` | `/compare` | Comparer deux exercices consécutifs |
| `DELETE` | `/reports/{id}` | Retirer un rapport terminé |

## Vérifier le projet

```powershell
.\.venv-reporting\Scripts\python.exe -m pytest -q
.\.venv-reporting\Scripts\python.exe -m ruff check app tests
.\.venv-reporting\Scripts\python.exe -m pytest -q -m browser
```

Le test navigateur nécessite l'installation préalable de Chromium :

```powershell
.\.venv-reporting\Scripts\python.exe -m playwright install chromium
```

## Limites assumées

SQLite et un seul worker conviennent à une démonstration locale ou à une petite
équipe. Une mise en production multi-utilisateur demanderait une authentification
par compte, une base serveur et une file de tâches dédiée. Les analyses et les
alertes sont des aides au contrôle, jamais une certification comptable.
