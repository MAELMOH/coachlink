# CoachLink — Backlog partagé

Liste de travail partagée de l'équipe multi-agents. Chaque teammate coche/complète ses tâches
et peut ajouter des sous-tâches dans sa section. Ne pas supprimer les tâches des autres — marquer
`[x]` fait, `[~]` en cours, `[ ]` à faire, `[!]` bloqué (préciser pourquoi).

Statut Jira : **opérationnel**. Projet `SCRUM` sur `coachlink.atlassian.net`, miroir de ce fichier :
SCRUM-5 (Phase 0, terminé), SCRUM-6 (Phase 1/DevOps), SCRUM-7 (Phase 2/Backend), SCRUM-8
(Phase 3/Front), SCRUM-9 (Phase 4/QA), SCRUM-10 (Phase 5/Déploiement), chacun avec ses tickets
enfants. Ce fichier reste la référence rapide pour l'équipe ; mettez à jour Jira en plus si vous
avez le temps (pas obligatoire), sinon le chef de projet resynchronisera périodiquement.

> **Lire `ARCHITECTURE.md` avant de coder.** Stack figée : Flutter (mobile) · FastAPI/Python 3.12
> (backend) · PostgreSQL 16 + Redis 7 + S3 Scaleway Paris · mono-repo `backend/` + `mobile/` + `docs/`.
> Toute question d'architecture → `SendMessage({to: "techlead", ...})`.

---

## Phase 0 — Cadrage & architecture (bloquant pour les phases 2-4)

- [x] **[Chef de projet]** Spécifications fonctionnelles détaillées → `docs/specs-fonctionnelles.md`
      (user stories coach/client, règles métier : essai gratuit 10j, présentiel vs distance,
      commission par client actif — 3 sous-questions posées explicitement, cf. §2.3 et §7 du doc)
- [x] **[Chef de projet]** Trancher la définition de « client actif » → **fait le 2026-09-23**,
      voir `ARCHITECTURE.md` ADR-011. Reste ouvert : IAP Apple/Google vs Stripe (§7, SCRUM-2)
- [x] **[Tech Lead]** Choix stack mobile + backend + DB → documenté dans `ARCHITECTURE.md`
- [x] **[Tech Lead]** Décision bibliothèque d'exercices — licences réellement vérifiées :
      ExerciseDB gratuit = **non-commercial** ❌, Wger = **CC-BY-SA share-alike** ❌,
      **free-exercise-db (Unlicense, domaine public)** ✅ retenu comme seed + upload vidéo par coach
- [x] **[Tech Lead]** Modèle de données initial (24 entités) → `ARCHITECTURE.md` §4
- [x] **[Tech Lead]** Stratégie RGPD dès la conception → `ARCHITECTURE.md` §5
      (envelope encryption AES-256-GCM, consentement bloquant, export/suppression, hébergement UE)
- [x] **[Tech Lead]** Design du système d'abonnement extensible → `ARCHITECTURE.md` §7
      (port `BillingProvider`, `ManualBillingProvider` au MVP, Stripe scaffoldé)
- [x] **[Tech Lead]** Recruter les teammates Front (mobile), Back, QA une fois la stack tranchée
- [ ] **[Tech Lead]** Rester disponible pour arbitrer les questions d'archi en cours de dev

## Phase 1 — Fondations (DevOps, démarre en parallèle de la phase 0)

- [x] Créer le repo GitHub, structure de base, README
      — remote créé : https://github.com/MAELMOH/coachlink (public), branche par défaut `main`.
      README complet, `.gitignore` adapté Flutter + Python. PR #1 (`feat/mobile-socle` → `main`)
      ouverte avec tout le travail à date ; fusion volontairement laissée à l'utilisateur humain
      (règle "pas de merge sans review humaine").
- [x] Structure mono-repo : `backend/` `mobile/` `docs/` `.github/workflows/` (voir `ARCHITECTURE.md` §3)
      — `docs/` et `.github/` créés par DevOps ; `backend/` et `mobile/` par `back` et `front`.
      Ajout de `infra/postgres/init/` (rôles + extensions, partagé dev/CI).
      Re-vérifié 2026-09-23 : conforme à l'arborescence cible.
- [x] Pipeline CI backend : `.github/workflows/ci-backend.yml` — `ruff check` + `ruff format --check`
      + `mypy app/domain` (strict) + `pytest` en deux passes (rapide sans services, puis complète)
      avec services Postgres 16 + Redis 7, Python épinglé 3.12, couverture `app.domain`/`app.services`.
- [x] Pipeline CI mobile : `.github/workflows/ci-mobile.yml` — `dart format --set-exit-if-changed`
      → `build_runner` → `flutter analyze --no-fatal-infos` → `flutter test test/`.
      `integration_test/` volontairement exclu (nécessite un émulateur, demande QA).
- [~] Protection de `main` (PR obligatoire, CI verte requise), Conventional Commits
      — branche `main` protégée créée : PR obligatoire, 0 approbation requise (pas de reviewer
      humain dispo), force-push et suppression de branche bloqués. **Pas encore de status check
      requis** — `ci-backend`/`ci-mobile` sont filtrés par `paths:` et bloqueraient indéfiniment
      une PR hors de leur périmètre si rendus required tels quels. Décision et solution
      (`ci-sentinel.yml`) : voir Journal des décisions, 2026-09-23. **Reste à faire par un humain**
      (accès admin GitHub / `gh` CLI non disponibles depuis l'agent DevOps) : dans Settings →
      Branches → règle de `main`, cocher "Require status checks to pass" et ajouter `PR sanity
      (toujours déclenché)` (job `sentinel` de `ci-sentinel.yml`) comme check requis.
- [x] `docker-compose.yml` dev local : Postgres 16, Redis 7, MinIO (S3-compatible)
      — **démarré et vérifié réellement** : 3 conteneurs `healthy`, buckets privés créés,
      extensions `citext`/`pgcrypto` installées, et isolation RLS testée de bout en bout.
- [ ] Environnement dev/staging (hébergement UE, Scaleway Paris) — ne rien provisionner sans
      validation explicite du chef de projet

## Phase 2 — Backend (Agent `back`, débloqué après Phase 0)

### 2.1 Socle
> **Vérifié en exécution le 2026-09-23** (pas seulement écrit) : `alembic upgrade head`
> puis `downgrade base` puis `upgrade head` sur un vrai PostgreSQL 16, `alembic check`
> sans dérive, app démarrée (`/health`, `/health/ready` avec check DB, `/openapi.json`,
> erreurs normalisées), `ruff check` + `ruff format --check` + `mypy app/domain` propres,
> **18/18 tests RLS verts**. Détail des bugs trouvés : commit `fc02349`.

- [x] Squelette FastAPI (`app/api/v1`, `app/domain`, `app/models`, `app/schemas`, `app/services`, `app/core`)
- [x] Config par variables d'environnement (Pydantic Settings) + `.env.example`
      — bug corrigé : `COACHLINK_CORS_ORIGINS=` vide faisait planter le démarrage
      (pydantic-settings JSON-décode avant les validators) ⇒ `cp .env.example .env`
      donnait une app qui ne bootait pas. Corrigé via `Annotated[list[str], NoDecode]`.
- [x] SQLAlchemy 2.0 async + Alembic, migration initiale des 24 entités (§4)
      — la chaîne de migrations n'avait jamais été appliquée. 2 bugs corrigés :
      `user_account.email` déclaré `Text` dans le modèle mais converti en `citext` par
      la migration (dérive `alembic check`, et le prochain `--autogenerate` aurait
      rétabli la sensibilité à la casse sur les e-mails) ; extension `citext` supposée
      présente alors que seul le 1er démarrage du conteneur dev l'installe (CI,
      testcontainer et Scaleway échouaient) — la migration porte désormais ses prérequis.
- [x] Policies PostgreSQL **Row Level Security** sur les tables client (défense en profondeur)
      — **la seconde barrière est maintenant réellement démontrée**, elle ne l'était pas :
      la suite construisait son schéma avec `Base.metadata.create_all()`, qui n'émet
      aucune policy. Le schéma de test vient désormais d'Alembic (`tests/support/schema.py`),
      donc chaque run reteste aussi la chaîne de migrations. Prouvé en SQL brut sous le
      rôle `coachlink_app` (NOSUPERUSER/NOBYPASSRLS) : lecture ET écriture croisées
      coach A → client de coach B bloquées, `paused`/`revoked`/`pending` coupent l'accès
      du coach, le client garde l'accès à ses propres données.
- [x] Middleware : erreurs normalisées, request-id, `structlog` **sans PII**, rate limiting
- [x] _(ajout back)_ `app/domain/ids.py` : UUID v7 généré côté applicatif (pas natif en PG16)
      — RFC 9562, compteur monotone intra-milliseconde (requis par la pagination cursor
      §8), `mypy --strict` OK, 12 tests unitaires verts. **SCRUM-4 → Terminé.**

> **Notes d'environnement (pour `devops`)** — deux points rencontrés sur la machine de dev :
> 1. Le port **5432 était déjà pris par un PostgreSQL installé sur l'hôte Windows**, qui
>    répondait à la place du conteneur (échec opaque `ConnectionDoesNotExistError`).
>    Contourné en local via `POSTGRES_PORT=55432` dans le `.env` racine (non committé,
>    la variable existait déjà dans `docker-compose.yml`). À documenter dans le README.
> 2. `testcontainers` / `psycopg` / `pytest-xdist` sont déclarés dans les extras `dev`
>    du `pyproject.toml` mais n'étaient pas installés dans le venv local : les tests
>    RLS/intégration se *skippaient* silencieusement. Rien à corriger côté code.

### 2.2 Auth & lien coach-client
- [ ] `POST /auth/register` (role coach|client), `POST /auth/login`, `POST /auth/refresh` (rotatif), `POST /auth/logout`
- [ ] Argon2id + JWT access 15 min / refresh 30 j révocable
- [ ] `POST /coach/invitations` (code 8 car. + deep link), `GET /coach/invitations`
- [ ] `POST /invitations/{code}/accept` → crée `coach_client_link` (mode présentiel|distance)
- [ ] `GET /coach/clients` (vue multi-clients), `PATCH /links/{id}` (pause/révocation)
- [ ] Dépendance d'autorisation `require_active_link(coach, client)` + écriture `audit_log`

### 2.3 Exercices & programmes
- [ ] Script de seed du catalogue depuis **free-exercise-db (Unlicense)**, images rapatriées
      dans notre bucket UE (interdiction de hotlink), `media_license='public_domain'`
- [ ] `GET /exercises` (filtres muscle/équipement/recherche), `GET /exercises/{id}`
- [ ] `POST /exercises` (exercice propre au coach) + upload média via URL S3 pré-signée
- [ ] Worker Celery de transcodage vidéo (H.264 720p + vignette), validation taille/durée
- [ ] CRUD `/programs`, `/programs/{id}/sessions`, `/sessions/{id}/exercises`
- [ ] `POST /programs/{id}/publish` → publie au client + événement WS `program.published`
- [ ] Programmes modèles réutilisables (`client_id = NULL`) + duplication

### 2.4 Exécution & suivi
- [ ] `GET /me/today`, `GET /me/week` (programme du jour / de la semaine côté client)
- [ ] `POST /workout-logs` + `PATCH /set-logs/{id}` (cocher série, reps, charge) — **idempotent**
- [ ] Calcul du **volume** `Σ(reps × charge)` : fonction pure dans `app/domain`, dénormalisé sur `workout_log`
- [ ] `GET /clients/{id}/history` (historique complet des séances)
- [ ] CRUD `/measurements` (poids, mensurations) — **colonnes chiffrées**
- [ ] `/progress-photos` : upload chiffré, `shared_with_coach` **false par défaut**, URL pré-signée TTL 5 min
- [ ] `GET /clients/{id}/stats` : séries temporelles poids / force / volume (agrégation après déchiffrement)
- [ ] Détection et enregistrement des `personal_record` (1RM estimé)

### 2.5 Nutrition (optionnel par coach)
- [ ] CRUD `/nutrition-plans` + `/meals` (kcal, macros, repas types) — **colonnes chiffrées**
- [ ] `POST /nutrition-logs` (le client coche un repas suivi)
- [ ] Flag `coach_profile.offers_nutrition` → masque la feature de bout en bout

### 2.6 Messagerie & notifications
- [ ] `GET /conversations`, `GET/POST /conversations/{id}/messages` (corps **chiffré**)
- [ ] WebSocket `/ws` (JWT) + Redis Pub/Sub, canaux `user:{id}` / `link:{id}`, reconnexion
- [ ] Messagerie **désactivée** si `coaching_mode = presentiel`
- [ ] `POST /devices` (device token), push **data-only sans PII** `{"n": "<uuid>"}` via FCM/APNs
- [ ] Rappels de séance planifiés (Celery beat) + `GET /notifications`

### 2.7 RGPD & facturation
- [ ] `GET/POST /me/consents` (tos, privacy, health_data, progress_photos, marketing)
- [ ] Garde globale `403 CONSENT_REQUIRED` tant que les consentements obligatoires manquent
- [ ] Service d'envelope encryption (KEK/DEK, AES-256-GCM, AAD `table:row:column`) + rotation
- [ ] `POST /me/data-export` → ZIP JSON+médias, lien pré-signé 24 h (Celery)
- [ ] `POST /me/delete-account` → rétractation 7 j puis purge physique + **crypto-shredding**
- [ ] Anonymisation des comptes inactifs 24 mois (Celery beat)
- [ ] Port `BillingProvider` + `ManualBillingProvider` (essai 10 j, lecture seule à l'expiration)
- [ ] `StripeBillingProvider` **scaffoldé** (`NotImplementedError`, tests `skip`)
- [ ] Job mensuel `active_client_snapshot` (idempotent) + `GET /coach/billing/summary`
- [ ] `/webhooks/billing` : vérification de signature + idempotence par `provider_event_id`

### 2.8 Contrat
- [ ] OpenAPI propre et exposé en dev → génération des modèles Dart pour `front`
- [ ] `GET /sync?since=` (deltas offline), conflits : LWW par champ sauf `set_log` (le client fait foi)

## Phase 3 — Mobile Front (Agent `front`, débloqué après Phase 0)

### 3.1 Socle
- [ ] Projet Flutter, arborescence `core/` + `features/<feature>/{data,domain,presentation}`
- [ ] Riverpod, `go_router` (deep link invitation), thème clair/sombre, i18n ARB (FR)
- [ ] Client `dio` + interceptor de refresh token, gestion des erreurs normalisées
- [ ] Drift + SQLCipher (base locale chiffrée), `flutter_secure_storage`, purge au logout
- [ ] File de synchronisation offline (rejeu idempotent via `Idempotency-Key`)
- [ ] Client WebSocket avec reconnexion et backoff exponentiel

### 3.2 Onboarding & compte (commun)
- [ ] Inscription / connexion, choix du rôle coach ou client
- [ ] **Écran de consentement RGPD bloquant** (granulaire, photos et marketing séparés et opt-in)
- [ ] Écran « Mes données » : révocation de consentement, export, suppression de compte
- [ ] Bandeau d'essai gratuit 10 jours + écran de fin d'essai (mode lecture seule)

### 3.3 Parcours coach
- [ ] Dashboard multi-clients (état de chaque client, séances de la semaine, alertes d'inactivité)
- [ ] Invitation client : génération/partage du code et du lien, choix présentiel ou à distance
- [ ] Fiche client : mensurations, photos (si partagées), performances, séances réalisées
- [ ] Éditeur de programme : séances, exercices, séries/reps/charge/repos/tempo, réordonnancement
- [ ] Bibliothèque d'exercices : recherche, filtres muscle/équipement, détail avec média
- [ ] Création d'exercice propre + upload image/vidéo (progression d'upload, limites de taille)
- [ ] Plans alimentaires (affiché seulement si `offers_nutrition`)
- [ ] Messagerie (masquée en mode présentiel)

### 3.4 Parcours client
- [ ] Écran « Ma séance du jour » + vue semaine
- [ ] Mode exécution : cocher chaque série, saisir reps et charge, minuteur de repos, **fonctionne hors ligne**
- [ ] Détail d'exercice : image/vidéo de bonne exécution, consignes, notes du coach
- [ ] Saisie de poids et mensurations, photos de progression avec contrôle de partage explicite
- [ ] Graphiques de progression (`fl_chart`) : poids, charge, volume, records
- [ ] Historique des séances
- [ ] Plan alimentaire du jour + validation des repas
- [ ] Messagerie avec le coach

### 3.5 Transverse
- [ ] Notifications push (permission, token, deep link, **contenu récupéré via l'API**)
- [ ] États vides, squelettes de chargement, gestion du mode hors ligne, accessibilité
- [ ] Certificate pinning sur le domaine d'API

## Phase 4 — QA (Agent `qa`, en continu dès que du code existe, pas juste à la fin)

- [ ] Mettre en place l'infra de test dès le squelette : `pytest` + `pytest-asyncio` + `httpx.AsyncClient`
      + `testcontainers` (Postgres réel), fixtures et factories de données
- [ ] Seuil de couverture backend ≥ 80 % sur `app/domain` et `app/services`, câblé dans la CI avec `devops`
- [ ] Tests unitaires du **calcul de volume** (`Σ reps × charge`) — cas limites : 0 rep, poids du corps, séries partielles
- [ ] Tests unitaires de `is_client_active()` (règle de commission) et des transitions d'essai 10 j
- [ ] Tests du service de chiffrement : round-trip, AAD invalide rejetée, crypto-shredding effectif
- [ ] **Tests d'isolation (priorité 1)** : coach A ne doit jamais lire les données d'un client de coach B —
      via l'API *et* directement via RLS ; lien `paused`/`revoked` ⇒ accès refusé
- [ ] Tests du consentement bloquant : `403 CONSENT_REQUIRED` sur toutes les routes métier
- [ ] Tests d'intégration API par domaine (auth, invitation, programmes, logs, mesures, nutrition, messagerie)
- [ ] Tests des photos de progression : non visibles du coach sans `shared_with_coach = true`
- [ ] Tests d'idempotence (`POST /workout-logs` rejoué) et de résolution de conflits `/sync`
- [ ] Tests WebSocket : diffusion sur le bon canal, aucune fuite inter-liens
- [ ] Tests unitaires front (Riverpod, mapping, logique offline) + widget tests des écrans clés
- [ ] Tests d'intégration Flutter des parcours critiques : invitation → lien → programme reçu →
      séance complétée hors ligne → synchronisation → progression visible côté coach
- [ ] Vérification RGPD de bout en bout : export complet et lisible, suppression réellement physique,
      révocation de consentement effective, **aucune PII dans les logs ni dans les payloads push**
- [ ] Rapport de qualité tenu à jour dans `docs/qa/` (bugs ouverts, couverture, risques)

## Phase 5 — Déploiement (DevOps)

- [ ] Environnement staging fonctionnel et accessible (UE)
- [ ] Documentation de déploiement
- [ ] Gestion des secrets (KEK dans Scaleway Secret Manager, jamais dans le repo)
- [ ] Sauvegardes Postgres chiffrées + test de restauration
- [ ] Sentry région UE, alerting

---

## Journal des décisions

_(Tech Lead / chaque agent : consigner ici les décisions importantes avec la date et la justification)_

- **2026-09-23 [Back]** Section 2.1 (socle) terminée et **vérifiée en exécution**, pas
  seulement relue. Le constat de départ : tout le code du socle était écrit et le lint
  était propre, mais **rien n'avait jamais été exécuté** — aucune migration appliquée sur
  une vraie base, et la suite de tests construisait son schéma avec
  `Base.metadata.create_all()`, qui n'émet ni policy RLS, ni `citext`, ni trigger. Les
  18 tests RLS étaient donc skippés ou rouges : la « seconde barrière », que
  `ARCHITECTURE.md` §4 désigne comme le risque n°1 du projet, n'avait jamais été
  démontrée. Elle l'est maintenant (commit `fc02349`).

  **Décision structurante** : le schéma de test est désormais construit par **Alembic**
  et non par `create_all` (`tests/support/schema.py`). `create_all` ne connaît que les
  tables et les index ; tout ce qui protège réellement les données (policies RLS,
  `FORCE ROW LEVEL SECURITY`, `citext` sur l'e-mail, trigger `updated_at` dont dépend
  `GET /sync?since=`, fonction `resolve_invitation`) vit en dehors des métadonnées ORM.
  Effet de bord voulu : chaque run de tests reteste aussi la chaîne de migrations, donc
  une migration qui ne s'applique pas proprement est vue ici et pas en staging.

  4 bugs réels trouvés **parce qu'on a exécuté** (détail dans la section 2.1) : boot
  impossible avec un `.env` issu de `.env.example` ; dérive modèle/migration sur
  `email` qui aurait silencieusement rétabli la sensibilité à la casse ; extension
  `citext` non créée par la migration ; tests RLS visant une table `"user"` qui n'existe
  pas (elle s'appelle `user_account`) et utilisant `SET LOCAL app.current_role`, qui est
  une **erreur de syntaxe** en PostgreSQL (`current_role` est un mot réservé) — le code
  applicatif, lui, utilisait déjà `set_config()` et n'était pas touché.

  **Jira** : SCRUM-4 (UUID v7) peut passer en *Terminé*, SCRUM-3 (socle) également.
  Pas d'accès Jira vérifié depuis cette session — le chef de projet resynchronise.

- **2026-09-23 [DevOps]** Durcissement de la CI backend, suite aux retours de `back` (socle 2.1).
  Quatre changements, dont deux corrigent des bugs silencieux qui rendaient la CI trompeuse :

  1. **`alembic check` ajouté au job backend.** Demandé par `back` après une dérive réelle
     (`user_account.email` en `Text` côté modèle, converti en `citext` par la migration). Le vrai
     risque n'était pas le check rouge mais un futur `alembic revision --autogenerate` émettant un
     `ALTER COLUMN email TYPE text`, rétablissant silencieusement la sensibilité à la casse des
     e-mails (deux comptes `A@x.com` / `a@x.com`). Tourne sur une base **dédiée et vierge**
     (`coachlink_migrations_check`), pas sur `coachlink_test` que la suite pytest migre déjà
     elle-même — sinon le résultat dépendrait de l'ordre des étapes. Séquence vérifiée pour de
     vrai en local contre le Postgres du docker-compose : 3 migrations appliquées sur base vierge
     puis `No new upgrade operations detected`, exit 0.
  2. **Variables d'environnement de la CI corrigées : le préfixe `COACHLINK_` est obligatoire.**
     `Settings` (app/core/config.py) déclare `env_prefix="COACHLINK_"` avec `extra="ignore"` : les
     variables `DATABASE_URL`, `DATABASE_URL_OWNER`, `SECRET_KEY`, `ENCRYPTION_KEK` que la CI
     posait depuis le début **n'étaient lues par personne**, la config retombant sans bruit sur
     ses valeurs par défaut de dev. `ENVIRONMENT: ci` était faux deux fois : mauvais préfixe, et
     `"ci"` n'appartient pas au `Literal["dev","test","staging","prod"]`. Renommé en
     `COACHLINK_ENVIRONMENT=test`, `COACHLINK_DATABASE_URL`,
     `COACHLINK_DATABASE_MIGRATION_URL`, `COACHLINK_JWT_SECRET`, `COACHLINK_KEK_B64` (base64 de
     32 octets valide, sinon le service de chiffrement refuse de démarrer). Les variables
     `TEST_DATABASE_URL*` restent sans préfixe : elles sont lues directement par
     `tests/support/database.py`, pas par Pydantic.
  3. **Garde contre la « suite verte qui ne teste rien »** (`.github/scripts/assert_db_tests_ran.py`).
     Les tests `integration`/`rls` se skippent volontairement quand aucun PostgreSQL n'est
     joignable — bon choix (jamais de repli sur SQLite, où les policies RLS n'existent pas), mais
     pytest renvoie alors 0. Un service container mal démarré, une variable renommée ou des
     extras `dev` non installés (cas réellement vécu par `back` en local : `testcontainers` et
     `psycopg` absents → 18 tests RLS skippés en silence) suffisaient donc à afficher une CI verte
     n'ayant vérifié aucune garantie d'isolation. Le script relit le rapport JUnit et échoue si un
     test de `tests/rls/` ou `tests/integration/` a été skippé, ou si aucun n'a tourné. Testé sur
     4 cas (nominal, skip, répertoire vide, rapport absent).
  4. **Bug corrigé dans `ci-sentinel.yml` : le workflow était invalide depuis sa création.** La
     ligne `run: echo "Sentinelle CI : checkout OK..."` est un scalaire YAML nu contenant `": "`,
     que YAML interprète comme un séparateur clé/valeur → GitHub rejetait le fichier entier. Le
     check censé devenir le status check requis n'aurait donc jamais tourné : exactement le
     blocage qu'il existe pour empêcher. Passé en bloc littéral `|`, et les 3 workflows sont
     désormais validés au parse YAML. **Conséquence sur la consigne d'activation du check
     requis** : attendre que `ci-sentinel.yml` apparaisse vert sur la PR #1 avant de le cocher
     comme required (il ne pouvait pas l'être avant ce correctif).

  Documenté aussi dans le README : section *Dépannage* (port 5432 déjà pris par un PostgreSQL
  hôte sous Windows → `POSTGRES_PORT=55432`, piège signalé par `back` qui coûte une heure faute
  de la moindre ligne dans les logs du conteneur ; et comment repérer une suite verte dont les
  tests RLS ont été skippés).

- **2026-09-23 [DevOps]** Reprise de session (agent DevOps précédent arrêté, non récupérable).
  État vérifié à froid : structure mono-repo conforme à `ARCHITECTURE.md` §3, remote GitHub
  `https://github.com/MAELMOH/coachlink` existant et protégé (PR obligatoire, 0 approbation
  requise, force-push/suppression bloqués), PR #1 (`feat/mobile-socle` → `main`) ouverte et non
  fusionnée (laissée à l'utilisateur, conformément à la règle "pas de merge sans review humaine").
  Continuation des commits sur `feat/mobile-socle` (pas de nouvelle branche : `main` n'a pas
  encore reçu la PR #1, repartir "propre" n'apporterait rien pour l'instant).

  **Piège des status checks requis, tranché** : `ci-backend.yml` et `ci-mobile.yml` sont filtrés
  par `paths:` (backend/**, mobile/**). Les rendre "required" dans la protection de `main` tels
  quels bloquerait indéfiniment toute PR hors de leur périmètre (docs/, ARCHITECTURE.md,
  TASKS.md, workflows eux-mêmes...) puisqu'aucun des deux ne se déclencherait — GitHub laisse un
  check required non déclenché en attente permanente, sans déblocage possible autrement qu'en
  changeant la config de protection. Option retenue : nouveau job **sentinelle**
  (`.github/workflows/ci-sentinel.yml`, job `sentinel`) SANS filtre de chemin, déclenché sur
  chaque PR quel que soit le scope, volontairement minimal (quelques secondes, vérifie juste que
  le titre de la PR respecte Conventional Commits). C'est ce job qui doit devenir le status check
  requis — garantit qu'il y a toujours un check qui se déclenche et se termine. `ci-backend` et
  `ci-mobile` restent en place et visibles mais PAS marqués required pour l'instant : les
  transformer en required reproduirait le même piège dès qu'une PR mono-scope arrive. Alternative
  écartée pour l'instant : un job d'agrégateur qui attend/poll les statuts des deux CI scopées via
  l'API GitHub Checks avant de répondre lui-même — plus correct (garantirait que le scope
  réellement modifié est vert avant merge) mais plus complexe à maintenir ; à reconsidérer si le
  volume de PR augmente ou si un merge sans CI scopée verte cause un incident.

  **Action humaine restante** (l'agent DevOps n'a pas d'accès `gh` CLI ni de token API GitHub
  dans cet environnement — tentative volontairement non contournée, voir note ci-dessous) :
  dans GitHub → Settings → Branches → règle de `main` → activer "Require status checks to pass
  before merging" et cocher le check `PR sanity (toujours déclenché)` (job `sentinel`). Idéalement
  fait après le premier passage de `ci-sentinel.yml` sur une PR (le check doit avoir tourné au
  moins une fois pour apparaître dans la liste GitHub).

  Jira : SCRUM-11 passé à *Terminé* (repo + structure + README réellement en place, remote créé).
  SCRUM-13 passé à *En cours* (docker-compose dev local vérifié ; staging Scaleway explicitement
  hors périmètre sans confirmation explicite de l'utilisateur, cf. règle permanente).

- **2026-09-23 [Chef de projet]** Définition de « client actif » figée (SCRUM-1 fermé) :
  lien actif, mois de création exclu (pas de prorata), client hors essai gratuit, ≥2 événements
  qualifiants/mois (séance complétée, mesure, message — combinaison libre, seuil relevé de 1 à 2
  sur demande explicite pour éviter qu'un client quasi inactif déclenche une commission). Détail :
  `ARCHITECTURE.md` ADR-011 et `docs/specs-fonctionnelles.md` §2.3. Reste ouvert : SCRUM-2
  (Stripe vs IAP).

- **2026-09-22 [Chef de projet]** Sprint 1 décidé (équipe en pause, seul le chef de projet
  travaille pour l'instant). Contenu : finir le cadrage bloquant + les fondations déjà en cours,
  plutôt que d'ouvrir Front/QA qui n'ont encore rien commencé. Label `sprint-1` posé sur les
  tickets Jira concernés (pas d'API de création de sprint disponible, donc pas de vrai sprint Jira
  créé — juste le marquage ; création du conteneur à faire manuellement dans l'UI) :
  SCRUM-1 (client actif), SCRUM-2 (Stripe vs IAP), SCRUM-35 (spécifications fonctionnelles,
  nouveau ticket), SCRUM-11 (repo/structure/README), SCRUM-3 + SCRUM-4 (socle backend).
  SCRUM-12 (pipeline CI) passé en Terminé car réellement fait et vérifié.

- **2026-09-22 [DevOps]** Repo git initialisé en local (`git init`, branche `main`), README.md et
  .gitignore génériques créés. Pas de remote GitHub créé/connecté pour l'instant — en attente
  d'un remote existant fourni par l'utilisateur ou d'une confirmation explicite avant d'en créer
  un (action visible publiquement, hors périmètre d'auto-décision DevOps). Structure interne du
  repo (mono-repo /mobile /backend pressenti) volontairement pas encore créée : en attente
  d'ARCHITECTURE.md du Tech Lead pour ne pas imposer une arborescence qui ne correspondrait pas à
  la stack retenue. Coordination lancée avec tech-lead (SendMessage) pour être notifié dès que
  ARCHITECTURE.md est prêt et dès que back/front/QA sont recrutés (pour caler le pipeline CI).

- **2026-09-22 [DevOps]** Structure mono-repo finalisée, CI et environnement de dev en place.
  Décisions et points de vigilance :
  - **Deux workflows séparés** (`ci-backend.yml`, `ci-mobile.yml`) plutôt qu'un seul avec des jobs
    conditionnels : c'est la façon la plus lisible d'obtenir le filtrage par chemins demandé par le
    Tech Lead, sans dépendre d'une action tierce. *Effet de bord à connaître au moment de protéger
    `main`* : un check requis qui n'est jamais déclenché (PR purement mobile ⇒ CI backend non
    lancée) bloque le merge. Il faudra soit ne rendre requis que des checks toujours déclenchés,
    soit ajouter un job « sentinelle ». À trancher quand le remote existera.
  - **Deux rôles PostgreSQL** (`coachlink_owner` / `coachlink_app` en `NOSUPERUSER NOBYPASSRLS`),
    script unique `infra/postgres/init/01-roles.sql` partagé entre le dev local et la CI — une seule
    source de vérité, pour que la CI teste bien la même configuration que celle des développeurs.
    Vérifié fonctionnellement : avec une policy RLS active, le rôle applicatif ne voit que ses
    propres lignes (1 ligne sur 2 dans le test d'accès croisé). La barrière est réelle.
  - **Seuil de couverture 80 % affiché mais NON bloquant** (`COVERAGE_ENFORCE=false`) sur demande
    de `qa` : le rendre bloquant alors que `app/domain` et `app/services` sont quasi vides mettrait
    la CI au rouge dès le premier commit sans rien apprendre. À basculer sur feu vert de `qa`.
  - **Code généré Dart non committé** (`*.g.dart`, `*.freezed.dart`) et régénéré via `build_runner`
    en local comme en CI (arbitrage demandé par `front`, validé) : évite les conflits de merge sur
    du code que personne ne relit. En CI, `dart format` est vérifié **avant** la génération, pour
    qu'un code généré non conforme au formateur ne fasse pas échouer la CI à tort.
  - **`integration_test/` exclu de la CI mobile** (nécessite un émulateur) — demande de `qa`.
  - Environnement de dev **démarré et validé réellement**, pas seulement écrit : Postgres 16, Redis 7
    et MinIO `healthy`, buckets privés créés, extensions `citext`/`pgcrypto` en place.
  - Toujours **aucun remote GitHub** : ni création ni push sans confirmation explicite de
    l'utilisateur. Tout le travail de l'équipe est committé en local en attendant.

### 2026-09-22 — Tech Lead — Stack technique figée
**Flutter (mobile) · FastAPI/Python 3.12 (backend) · PostgreSQL 16 + Redis 7 + S3 Scaleway Paris.**
Flutter parce que la cible est une app mobile réelle (pas une web app responsive) et que l'équipe
a déjà livré du Flutter. FastAPI pour la familiarité Python et le contrat OpenAPI qui sert de source
aux modèles Dart. **PostgreSQL plutôt que MongoDB** (écart assumé vs l'expérience du développeur) :
le domaine est fortement relationnel (programme → séance → série), la facturation à la commission
exige des agrégats transactionnels exacts, et surtout Row Level Security offre une seconde barrière
contre la fuite de données entre coachs — le risque numéro un de cette app. Détail : `ARCHITECTURE.md` §2.

### 2026-09-22 — Tech Lead — Mono-repo
Un seul repo avec `backend/`, `mobile/`, `docs/`. Équipe réduite, contrat d'API partagé, une PR peut
porter une migration et l'écran qui la consomme. Confirmé à `devops` : sa proposition d'arborescence
est validée telle quelle.

### 2026-09-22 — Tech Lead — Bibliothèque d'exercices : licences vérifiées, pas supposées
Vérification effectuée avant tout engagement. **ExerciseDB** : code AGPL-3.0 et dataset gratuit
**non-commercial** (les droits commerciaux sur les GIF sont vendus à part) → **écarté**.
**Wger** : app AGPL-3.0 et données **CC-BY-SA 3.0**, avec des licences d'images variables par exercice ;
le *share-alike* nous obligerait à republier notre catalogue dérivé → **écarté**.
**Retenu : `yuhonas/free-exercise-db` sous Unlicense (domaine public)** — ~873 exercices avec photos,
aucune restriction commerciale, aucune attribution obligatoire — comme catalogue de démarrage,
**complété par l'upload de vidéos par chaque coach** (garantie de droits dans les CGU coach).
Aucune vidéo tierce ne doit être téléchargée par qui que ce soit dans l'équipe. Les médias seed sont
rapatriés dans notre bucket UE (pas de hotlink). Le champ `media_license` sur chaque média rend
l'audit juridique possible et permet de racheter plus tard une licence commerciale sans refonte.

### 2026-09-22 — Tech Lead — RGPD by design
Envelope encryption AES-256-GCM par utilisateur (KEK au secret manager, DEK par utilisateur) sur
poids, mensurations, nutrition, messages et photos — ce qui donne gratuitement le crypto-shredding
à la suppression de compte. Consentement granulaire, versionné et **bloquant** (403 tant qu'il manque).
Hébergement et traitements exclusivement en UE. **Limite assumée et documentée** : FCM/APNs sont hors
UE et incontournables pour du push iOS/Android — mitigation par un payload **data-only sans aucune PII**,
le contenu réel étant récupéré via l'API authentifiée. DPIA requise avant tout staging avec de vrais
utilisateurs. Détail : `ARCHITECTURE.md` §5.

### 2026-09-22 — Tech Lead — Abonnement extensible sans l'implémenter
Port `BillingProvider` (Protocol Python) avec `ManualBillingProvider` réellement implémenté au MVP
(essai 10 j, passage en lecture seule, calcul des clients actifs) et `StripeBillingProvider` scaffoldé
mais non implémenté. Le reste de l'app ne connaît que l'interface. **Risque remonté au chef de projet** :
Apple et Google imposent leur achat in-app (15–30 %) pour un abonnement déverrouillant du contenu
dans l'app, ce qui est incompatible avec un encaissement Stripe direct — décision produit nécessaire
avant d'implémenter le paiement réel, sans impact sur le MVP. Détail : `ARCHITECTURE.md` §7.

### 2026-09-22 — Tech Lead — Équipe recrutée
Agents `front` (Flutter), `back` (FastAPI) et `qa` (tests en continu) recrutés, avec consigne de se
coordonner entre eux et avec `devops` via SendMessage. Ordre de démarrage : `back` pose le socle et
l'OpenAPI, `front` démarre en parallèle sur le socle mobile et les écrans qui ne dépendent pas encore
de l'API, `qa` met en place l'infra de test dès le squelette et écrit les tests au fil de l'eau.
