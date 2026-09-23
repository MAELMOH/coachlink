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
- [ ] **[Chef de projet]** Trancher la définition de « client actif » proposée par le Tech Lead
      (`ARCHITECTURE.md` §7) et le sujet IAP Apple/Google vs Stripe (§7, risque remonté)
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

- [~] Créer le repo GitHub (ou init local si pas encore de remote), structure de base, README
      — repo git local initialisé, README complet (stack réelle + instructions de dev vérifiées),
      `.gitignore` adapté Flutter + Python. **Reste uniquement le remote GitHub** : en attente
      d'une confirmation explicite de l'utilisateur (création + premier push = action publique).
- [x] Structure mono-repo : `backend/` `mobile/` `docs/` `.github/workflows/` (voir `ARCHITECTURE.md` §3)
      — `docs/` et `.github/` créés par DevOps ; `backend/` et `mobile/` par `back` et `front`.
      Ajout de `infra/postgres/init/` (rôles + extensions, partagé dev/CI).
- [x] Pipeline CI backend : `.github/workflows/ci-backend.yml` — `ruff check` + `ruff format --check`
      + `mypy app/domain` (strict) + `pytest` en deux passes (rapide sans services, puis complète)
      avec services Postgres 16 + Redis 7, Python épinglé 3.12, couverture `app.domain`/`app.services`.
- [x] Pipeline CI mobile : `.github/workflows/ci-mobile.yml` — `dart format --set-exit-if-changed`
      → `build_runner` → `flutter analyze --no-fatal-infos` → `flutter test test/`.
      `integration_test/` volontairement exclu (nécessite un émulateur, demande QA).
- [~] Protection de `main` (PR obligatoire, CI verte requise), Conventional Commits
      — conventions documentées (README) + `pull_request_template.md` avec checklist RLS/RGPD.
      La protection de branche elle-même ne peut être configurée qu'une fois le remote GitHub créé.
- [x] `docker-compose.yml` dev local : Postgres 16, Redis 7, MinIO (S3-compatible)
      — **démarré et vérifié réellement** : 3 conteneurs `healthy`, buckets privés créés,
      extensions `citext`/`pgcrypto` installées, et isolation RLS testée de bout en bout.
- [ ] Environnement dev/staging (hébergement UE, Scaleway Paris) — ne rien provisionner sans
      validation explicite du chef de projet

## Phase 2 — Backend (Agent `back`, débloqué après Phase 0)

### 2.1 Socle
- [~] Squelette FastAPI (`app/api/v1`, `app/domain`, `app/models`, `app/schemas`, `app/services`, `app/core`)
- [~] Config par variables d'environnement (Pydantic Settings) + `.env.example`
- [~] SQLAlchemy 2.0 async + Alembic, migration initiale des 24 entités (§4)
- [~] Policies PostgreSQL **Row Level Security** sur les tables client (défense en profondeur)
- [~] Middleware : erreurs normalisées, request-id, `structlog` **sans PII**, rate limiting
- [ ] _(ajout back)_ `app/domain/ids.py` : UUID v7 généré côté applicatif (pas natif en PG16)

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
