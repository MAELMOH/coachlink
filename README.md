# CoachLink

Application mobile mettant en relation un **coach sportif** et ses **clients** : création et suivi
de programmes d'entraînement, suivi de progression (poids, mensurations, photos, performances),
plans alimentaires optionnels, messagerie coach-client, et abonnement (essai gratuit 10 jours côté
client, commission par client actif côté coach).

> **État** : MVP en cours de construction. L'architecture est figée et documentée dans
> [`ARCHITECTURE.md`](./ARCHITECTURE.md) — c'est la source de vérité. Le backlog de l'équipe est
> dans [`TASKS.md`](./TASKS.md).

---

## Stack

| Couche | Choix | Pourquoi (résumé — détail en `ARCHITECTURE.md`) |
|---|---|---|
| Mobile | **Flutter 3.x / Dart** | iOS + Android depuis une base unique, offline-first (`drift` + SQLCipher) |
| Backend | **Python 3.12 / FastAPI** | Contrat OpenAPI, WebSocket natif, écosystème crypto mature |
| Base de données | **PostgreSQL 16** | Domaine fortement relationnel + **Row Level Security** (cloisonnement coach/client) |
| Cache / temps réel / files | **Redis 7** | Pub/Sub pour la sync coach↔client, broker Celery |
| Stockage médias | **S3-compatible** — Scaleway Object Storage (Paris) ; **MinIO** en local | Buckets privés, URLs pré-signées à TTL court |

**Contrainte non négociable — RGPD by design.** Les données manipulées (poids, mensurations, photos
corporelles, nutrition) sont des données de santé au sens large : chiffrement applicatif par colonne,
**hébergement exclusivement UE**, consentement explicite et bloquant, export et suppression natifs.
Voir `ARCHITECTURE.md` §5.

---

## Structure du repo (mono-repo)

```
CoachLink/
├── ARCHITECTURE.md          # Source de vérité technique (Tech Lead)
├── TASKS.md                 # Backlog partagé + journal des décisions
├── docker-compose.yml       # Environnement de dev local
├── .env.example             # Variables d'infra dev (à copier en .env)
├── backend/                 # API FastAPI  (app/api · domain · models · schemas · services · workers · core)
├── mobile/                  # App Flutter  (lib/core · lib/features/<feature>/{data,domain,presentation})
├── infra/postgres/init/     # Rôles PostgreSQL + extensions (dev & CI)
├── docs/                    # ADR, specs, conformité RGPD (registre, DPIA)
└── .github/workflows/       # CI — un workflow par cible
```

---

## Lancer le projet en dev

### 1. Prérequis

- **Docker** + Docker Compose (infra locale)
- **Python 3.12** (le backend impose `>=3.12` — une 3.10/3.11 ne suffit pas)
- **Flutter stable** (Dart SDK `>=3.5.0`)

### 2. Infrastructure locale

```bash
cp .env.example .env
docker compose up -d
docker compose ps        # postgres, redis et minio doivent être "healthy"
```

Cela démarre PostgreSQL 16 (`localhost:5432`), Redis 7 (`localhost:6379`) et MinIO
(API `localhost:9000`, console web `localhost:9001`), et crée automatiquement :

- les **deux rôles PostgreSQL** (voir encadré ci-dessous) ainsi que les extensions `citext` et `pgcrypto` ;
- les buckets **privés** `coachlink-media` et `coachlink-exports`.

> #### ⚠️ Deux rôles PostgreSQL, et c'est volontaire
> - `coachlink_owner` — propriétaire du schéma, **exécute les migrations Alembic**.
> - `coachlink_app` — rôle utilisé par l'API : `NOSUPERUSER`, **`NOBYPASSRLS`**.
>
> Un superuser PostgreSQL contourne **silencieusement** toute policy Row Level Security. Si
> l'application (ou les tests) tournaient avec le rôle propriétaire, notre seconde barrière contre
> la fuite transversale *coach A → client de coach B* serait purement décorative, et les tests RLS
> passeraient au vert **sans rien vérifier**. D'où la séparation stricte.
>
> Corollaire pour les migrations : toute table portant des données client doit déclarer
> `ENABLE ROW LEVEL SECURITY` **et** `FORCE ROW LEVEL SECURITY`, faute de quoi le propriétaire
> échappe à ses propres policies.

Arrêter l'infra : `docker compose down` (ajouter `-v` pour repartir de zéro, ce qui **rejoue** les
scripts de `infra/postgres/init/`).

#### Dépannage

**`ConnectionDoesNotExistError` / erreurs de connexion opaques, sans une seule ligne dans
`docker compose logs postgres`.** Symptôme typique d'un **autre** PostgreSQL déjà installé sur la
machine hôte et déjà à l'écoute sur le port 5432 : c'est lui qui répond, pas le conteneur, donc les
logs du conteneur restent muets pendant que l'authentification échoue. Cas rencontré sur un poste
Windows le 2026-09-23. Correctif : changer le port publié côté hôte dans le `.env` racine, la
variable est déjà prévue dans `docker-compose.yml` —

```bash
POSTGRES_PORT=55432
```

puis `docker compose up -d` et penser à répercuter le port dans les URLs de connexion
(`COACHLINK_DATABASE_URL`, `COACHLINK_DATABASE_MIGRATION_URL`, `TEST_DATABASE_URL`).
Pour confirmer le diagnostic avant de changer quoi que ce soit : `docker compose port postgres 5432`
donne le mapping réel du conteneur.

**La suite de tests passe « au vert » en quelques secondes.** Vérifier qu'elle n'a pas simplement
*skippé* les tests `integration` et `rls` : sans PostgreSQL joignable — ou sans les extras `dev`
installés (`pip install -e ".[dev]"`, qui apporte `testcontainers` et `psycopg`) — ces tests sont
volontairement skippés plutôt que rabattus sur SQLite, où les policies RLS n'existent pas. L'en-tête
du rapport pytest le dit explicitement (`coachlink: NO PostgreSQL -> …`). En CI ce mode d'échec est
bloqué par `.github/scripts/assert_db_tests_ran.py`.

### 3. Backend

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head          # migrations : à lancer avec le rôle owner
uvicorn app.main:app --reload
```

API sur `http://localhost:8000`, documentation OpenAPI sur `http://localhost:8000/docs`.

### 4. Mobile

```bash
cd mobile
flutter pub get
dart run build_runner build --delete-conflicting-outputs   # indispensable : le code généré n'est pas committé
flutter run
```

---

## Qualité & CI

La CI (GitHub Actions) est découpée par cible, chaque workflow ne se déclenchant que sur les
chemins qui le concernent — une PR backend ne lance pas Flutter, et inversement.

| Workflow | Déclencheurs | Étapes |
|---|---|---|
| `ci-backend.yml` | `backend/**`, `infra/postgres/**` | `ruff check` · `ruff format --check` · `mypy app/domain` (strict) · `pytest` (rapide puis complet) + couverture |
| `ci-mobile.yml` | `mobile/**` | `dart format --set-exit-if-changed` · `build_runner` · `flutter analyze` · `flutter test` |

Points à connaître :

- **Les tests backend tournent contre un vrai PostgreSQL 16**, jamais SQLite : la Row Level
  Security n'existe pas en SQLite, et c'est précisément ce qu'on doit tester.
- **Le code généré Dart (`*.g.dart`, `*.freezed.dart`) n'est pas committé** — il est régénéré en
  local et en CI. Cela évite les conflits de merge sur du code que personne ne relit.
- `mobile/integration_test/` n'est **pas** exécuté en CI standard (nécessite un émulateur).
- Le seuil de couverture (80 % sur `app/domain` et `app/services`) est pour l'instant **affiché mais
  non bloquant** : le rendre bloquant alors que ces packages sont quasi vides mettrait la CI au
  rouge sans rien apprendre à personne. Basculer `COVERAGE_ENFORCE` à `true` dans
  `.github/workflows/ci-backend.yml` quand la couverture réelle le permettra.

### Conventions

- **Branches** : `main` protégée ; branches `feat/<scope>-<sujet>`, `fix/…` ; PR obligatoire, CI verte requise.
- **Commits** : [Conventional Commits](https://www.conventionalcommits.org/) — `feat(backend): …`, `fix(mobile): …`, `chore(ci): …`.

---

## Sécurité & données personnelles

- **Aucun secret réel dans le repo.** Les fichiers `.env` sont ignorés par git ; seuls les
  `.env.example` (valeurs factices) sont versionnés. La KEK qui chiffre les données de santé vit
  dans un gestionnaire de secrets (Scaleway Secret Manager), jamais dans un fichier du dépôt.
- **Aucune donnée personnelle réelle** ne doit être chargée dans l'environnement de dev ou de
  staging — jeux de données fictifs uniquement.
- Les identifiants présents dans `docker-compose.yml` et `.env.example` sont des valeurs de
  développement volontairement triviales et publiques ; elles ne doivent jamais être réutilisées
  ailleurs.

---

## Équipe

Projet construit par une équipe multi-agents : chef de projet, tech lead, backend, mobile, QA, devops.
