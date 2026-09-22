# CoachLink — Architecture technique

> Document de référence de l'équipe. Auteur : Tech Lead. Dernière mise à jour : **2026-09-22**.
> Toute décision structurante est également consignée dans `TASKS.md` → « Journal des décisions ».
> Les agents Front / Back / QA / DevOps doivent considérer ce document comme la source de vérité.
> Toute demande de dérogation passe par le Tech Lead via `SendMessage({to: "techlead", ...})`.

---

## 1. Contraintes qui pilotent l'architecture

| # | Contrainte | Conséquence architecturale |
|---|---|---|
| C1 | Application **mobile native/cross-platform**, pas une web app responsive | Flutter (binaire iOS/Android), pas de PWA |
| C2 | **RGPD by design** : poids, mensurations, photos corporelles, nutrition = données de santé au sens large | Chiffrement applicatif par colonne, hébergement UE exclusif, consentement bloquant, export/suppression natifs |
| C3 | **Sync coach ↔ client** quasi temps réel (programme poussé, séance cochée, messagerie) | WebSocket + Redis Pub/Sub, pas de polling |
| C4 | Médias d'exercices **juridiquement sûrs pour un usage commercial** | Voir §6 — seed domaine public + upload coach |
| C5 | Modèle éco : **commission par client actif** + essai client 10 j | Abstraction `BillingProvider`, notion de « client actif » calculée côté back |
| C6 | Usage terrain en salle : **réseau instable** | Offline-first côté mobile, file de synchronisation |

---

## 2. Stack retenue

### 2.1 Mobile — **Flutter 3.x / Dart**

- **Pourquoi** : une seule base de code iOS + Android avec un rendu réellement natif (Impeller), ce qui satisfait C1. Le développeur humain a déjà livré un front client en Flutter → coût d'entrée quasi nul.
- **Pourquoi pas React Native** : la familiarité React de l'équipe est réelle, mais l'écosystème graphiques/offline de Flutter (`fl_chart`, `drift`) est plus homogène, et le rendu est plus prévisible sur le parc Android bas de gamme typique d'une clientèle « salle de sport ».
- **Pourquoi pas du natif Kotlin + Swift** : deux fois le coût pour zéro besoin exotique (pas d'AR, pas de capteurs avancés au MVP).

Librairies cadrées (à ne pas remplacer sans validation Tech Lead) :

| Besoin | Choix | Note |
|---|---|---|
| State management | `riverpod` | Testable sans widget tree, injection simple |
| Navigation | `go_router` | Deep links pour l'invitation client |
| HTTP | `dio` + interceptor refresh token | Retry/backoff centralisé |
| Base locale offline | `drift` (SQLite) | Chiffrée via `sqlcipher_flutter_libs` |
| Secrets device | `flutter_secure_storage` | Keychain iOS / Keystore Android |
| Graphiques progression | `fl_chart` | Poids, force, volume |
| Temps réel | `web_socket_channel` | Reconnexion + backoff exponentiel |
| Modèles/serialisation | `freezed` + `json_serializable` | Immuabilité, égalité structurelle |
| i18n | `flutter_localizations` + ARB | FR par défaut, EN prévu |

### 2.2 Backend — **Python 3.12 / FastAPI**

- **Pourquoi** : familiarité maximale du développeur humain, typage Pydantic v2 qui documente l'API (OpenAPI) et sert de contrat pour générer les modèles Dart, support ASGI natif pour les WebSockets (C3), et un écosystème crypto/`cryptography` mature pour C2.
- **Pourquoi pas Spring Boot** : compétence présente mais vélocité moindre au MVP et empreinte d'exécution plus lourde pour un budget d'hébergement de démarrage.
- **Pourquoi pas Node/NestJS** : rien à y gagner face à la familiarité Python de l'équipe.

| Besoin | Choix |
|---|---|
| Framework | FastAPI + Uvicorn (Gunicorn en prod) |
| ORM / migrations | SQLAlchemy 2.0 (async) + Alembic |
| Validation | Pydantic v2 |
| Auth | JWT access (15 min) + refresh rotatif (30 j, révocable), hash **Argon2id** |
| Tâches asynchrones | Celery + Redis (rappels de séance, export RGPD, purge) |
| Temps réel | WebSocket FastAPI + Redis Pub/Sub (multi-worker) |
| Tests | `pytest`, `pytest-asyncio`, `httpx.AsyncClient`, `testcontainers` (Postgres réel) |
| Qualité | `ruff` (lint + format), `mypy --strict` sur `app/domain` |

### 2.3 Base de données — **PostgreSQL 16**

**Écart assumé vs l'expérience MongoDB du développeur.** Justification :

1. Le domaine est **fortement relationnel** : `programme → séance → bloc d'exercice → série effectuée`, plus le lien coach↔client qui conditionne *tous* les droits d'accès. Les jointures et les contraintes d'intégrité référentielle sont la règle, pas l'exception.
2. **RGPD** : PostgreSQL offre `pgcrypto`, le chiffrement transparent au niveau disque chez les hébergeurs UE, et surtout **Row Level Security** — une défense en profondeur contre la fuite transversale coach A → client de coach B, qui est *le* risque numéro un de cette app.
3. **Facturation** : la commission par client actif exige des agrégats transactionnels exacts. Le modèle transactionnel de Postgres l'assure sans effort.
4. `JSONB` couvre les rares besoins de schéma souple (snapshot de programme, préférences, payload d'audit) sans introduire une seconde base.

Autres briques :

| Rôle | Choix | Localisation |
|---|---|---|
| Cache / Pub-Sub / broker Celery | Redis 7 | UE |
| Stockage médias (photos, vidéos) | S3-compatible **Scaleway Object Storage (Paris)**, SSE-S3 activé, buckets privés + URLs pré-signées à TTL court (5 min) | Paris, FR |
| Hébergement applicatif | **Scaleway** (Paris/Amsterdam) — alternative : OVHcloud | UE |
| Observabilité | Sentry *self-hosted ou région UE*, logs structurés `structlog` **sans PII** | UE |

> **Règle ferme** : aucun service tiers hors UE ne doit *stocker* de donnée personnelle. Voir §5.4 pour le cas des notifications push.

### 2.4 Schéma d'ensemble

```
┌───────────────────────┐        ┌───────────────────────┐
│  Flutter — Coach      │        │  Flutter — Client     │
│  Drift (SQLCipher)    │        │  Drift (SQLCipher)    │
└──────────┬────────────┘        └──────────┬────────────┘
           │  HTTPS (TLS 1.3) REST + WSS               │
           └───────────────┬───────────────────────────┘
                           ▼
                 ┌──────────────────────┐
                 │  API FastAPI (UE)    │
                 │  Auth · RLS · Crypto │
                 └───┬─────────┬────────┘
                     │         │
          ┌──────────▼──┐  ┌───▼────────┐   ┌───────────────┐
          │ PostgreSQL  │  │  Redis     │   │ Object Storage│
          │  (Paris)    │  │ PubSub/Cel │   │   (Paris)     │
          └─────────────┘  └────────────┘   └───────────────┘
```

---

## 3. Structure du repo — **mono-repo**

Un seul repo GitHub. Justification : équipe réduite, contrat d'API partagé entre mobile et backend, une PR peut porter une migration + l'écran qui la consomme, et la CI voit l'ensemble. Le découpage en multi-repo serait du coût sans bénéfice à ce stade.

```
CoachLink/
├── ARCHITECTURE.md
├── TASKS.md
├── README.md
├── backend/
│   ├── app/
│   │   ├── api/v1/            # routers FastAPI (un fichier par domaine)
│   │   ├── domain/            # logique métier pure, testable sans I/O
│   │   ├── models/            # SQLAlchemy
│   │   ├── schemas/           # Pydantic (contrat API)
│   │   ├── services/          # orchestration (crypto, billing, storage, push)
│   │   ├── workers/           # tâches Celery
│   │   └── core/              # config, sécurité, crypto, dépendances
│   ├── alembic/
│   ├── tests/                 # unit/ · integration/ · e2e/
│   └── pyproject.toml         # ruff, mypy, pytest
├── mobile/
│   ├── lib/
│   │   ├── core/              # réseau, stockage sécurisé, thème, i18n
│   │   ├── features/<feature>/{data,domain,presentation}/
│   │   └── main.dart
│   ├── test/ · integration_test/
│   └── pubspec.yaml
├── docs/                      # ADR, specs fonctionnelles, RGPD (registre, DPIA)
└── .github/workflows/         # CI (DevOps)
```

**Convention de branches** : `main` protégée, branches `feat/<scope>-<sujet>`, `fix/…`, PR obligatoire, CI verte requise.
**Commits** : Conventional Commits (`feat(backend): …`), pour que DevOps puisse générer le changelog.

---

## 4. Modèle de données initial

Conventions : PK `UUID v7`, `created_at`/`updated_at` en `timestamptz` UTC, suppression logique (`deleted_at`) **sauf** exercice du droit à l'effacement qui est une suppression physique (§5.3). Les colonnes marquées 🔒 sont chiffrées applicativement (§5.1).

### Identité & relation

- **user** — `id`, `email` (unique, citext), `password_hash` (Argon2id), `role` (`coach` | `client`), `first_name`, `last_name`, `locale`, `timezone` (IANA, ex. `Europe/Paris`, défaut `Europe/Paris`), `email_verified_at`, `last_login_at`, `deleted_at`
  → `timezone` est **obligatoire** : « la séance d'aujourd'hui » se calcule dans le fuseau de l'utilisateur, pas en UTC. Le mobile renseigne le fuseau du device à la connexion.
- **coach_profile** — `user_id` (FK 1-1), `bio`, `specialties[]`, `offers_nutrition` (bool), `default_coaching_mode` (`presentiel` | `distance`)
- **client_profile** — `user_id` (FK 1-1), `birth_date` 🔒, `sex`, `height_cm` 🔒, `goal`, `trial_ends_at`
- **coach_client_link** — `id`, `coach_id`, `client_id`, `status` (`pending` | `active` | `paused` | `revoked`), `coaching_mode` (`presentiel` | `distance`), `started_at`, `ended_at`
  → *unicité* : un client n'a qu'un seul lien `active` à la fois.
- **invitation** — `id`, `coach_id`, `code` (8 car. lisibles, unique), `email_hint`, `expires_at`, `consumed_at`, `consumed_by`

> `coaching_mode = presentiel` ⇒ messagerie désactivée et suivi simplifié (pas de séance à cocher obligatoire). `distance` ⇒ messagerie + suivi complet.

### Entraînement

- **exercise** — `id`, `owner_coach_id` (NULL = catalogue global), `name`, `description`, `primary_muscles[]`, `secondary_muscles[]`, `equipment`, `mechanic`, `force`, `image_keys[]`, `video_key`, `media_license` (`public_domain` | `coach_owned`), `source` (`seed` | `coach`), `is_public`
- **program** — `id`, `coach_id`, `client_id` (NULL = modèle réutilisable), `name`, `description`, `starts_on`, `ends_on`, `status` (`draft` | `published` | `archived`)
- **program_session** — `id`, `program_id`, `name`, `day_index` *(ou* `scheduled_date`*)*, `order`, `notes`
- **session_exercise** — `id`, `program_session_id`, `exercise_id`, `order`, `target_sets`, `target_reps`, `target_load_kg`, `rest_seconds`, `tempo`, `coach_notes`
- **workout_log** — `id`, `client_id`, `program_session_id`, `performed_at`, `status` (`planned` | `in_progress` | `completed` | `skipped`), `duration_seconds`, `client_notes`, `rpe`, `total_volume_kg` *(dénormalisé, recalculé à chaque écriture de set_log)*
- **set_log** — `id`, `workout_log_id`, `session_exercise_id`, `set_index`, `reps_done`, `load_kg`, `is_completed`, `rest_taken_seconds`
  → **volume** = `Σ(reps_done × load_kg)` par exercice / séance / semaine. Calcul autorité **backend** ; le mobile peut l'estimer en offline pour l'affichage, le serveur fait foi à la synchro.

### Suivi & mesures (données sensibles)

- **body_measurement** — `id`, `client_id`, `measured_at`, `weight_kg` 🔒, `body_fat_pct` 🔒, `waist_cm` 🔒, `hip_cm` 🔒, `chest_cm` 🔒, `arm_cm` 🔒, `thigh_cm` 🔒, `source` (`client` | `coach`)
- **progress_photo** — `id`, `client_id`, `taken_at`, `storage_key`, `angle` (`front` | `side` | `back`), `shared_with_coach` (bool, **défaut `false`**), `consent_id`
- **personal_record** — `id`, `client_id`, `exercise_id`, `achieved_at`, `reps`, `load_kg`, `estimated_1rm`

### Nutrition (optionnelle par coach)

- **nutrition_plan** — `id`, `coach_id`, `client_id`, `name`, `kcal_target` 🔒, `protein_g` 🔒, `carbs_g` 🔒, `fat_g` 🔒, `starts_on`, `ends_on`, `status`
- **meal** — `id`, `nutrition_plan_id`, `slot` (`breakfast` | `lunch` | `dinner` | `snack`), `order`, `name`, `description`, `kcal` 🔒, `macros` (JSONB) 🔒
- **nutrition_log** — `id`, `client_id`, `meal_id`, `date`, `followed` (bool), `comment` 🔒

### Communication & facturation

- **conversation** — `id`, `coach_client_link_id`, `last_message_at`
- **message** — `id`, `conversation_id`, `sender_id`, `body` 🔒, `attachment_key`, `sent_at`, `read_at`
- **notification** — `id`, `user_id`, `type`, `payload` (JSONB, **sans PII**), `scheduled_for`, `sent_at`, `read_at`
- **device_token** — `id`, `user_id`, `platform` (`ios` | `android`), `token`, `last_seen_at`
- **subscription** — `id`, `subject_type` (`client` | `coach`), `subject_id`, `plan_code`, `status` (`trialing` | `active` | `past_due` | `canceled`), `trial_ends_at`, `current_period_start/end`, `provider` (`manual` | `stripe`), `provider_ref`
- **billing_event** — `id`, `subscription_id`, `type`, `amount_cents`, `currency`, `occurred_at`, `raw_payload` (JSONB)
- **active_client_snapshot** — `id`, `coach_id`, `client_id`, `period_month`, `is_active`, `computed_at` → base de la commission (§7)

### RGPD (tables de conformité)

- **consent** — `id`, `user_id`, `purpose` (`tos` | `privacy` | `health_data` | `progress_photos` | `marketing`), `granted` (bool), `version`, `granted_at`, `revoked_at`, `ip_hash`, `user_agent`
- **data_request** — `id`, `user_id`, `type` (`export` | `deletion`), `status`, `requested_at`, `completed_at`, `export_key`, `expires_at`
- **audit_log** — `id`, `actor_id`, `action`, `resource_type`, `resource_id`, `occurred_at`, `ip_hash` → **obligatoire** sur tout accès coach aux données sensibles d'un client.

### Règle d'accès transversale

Un coach n'accède aux données d'un client **que** via un `coach_client_link` en statut `active`. Cette règle est appliquée **deux fois** : dans la couche service FastAPI *et* par une policy PostgreSQL Row Level Security. La QA doit tester la tentative d'accès croisé comme un cas nominal, pas comme un cas exotique.

---

## 5. Stratégie RGPD concrète

Rôles : l'éditeur de CoachLink est **responsable de traitement** pour les comptes et la facturation, et **sous-traitant** pour les données que le coach traite sur ses clients. Un contrat de sous-traitance (art. 28) devra être annexé aux CGU — à produire côté juridique, hors périmètre dev, mais le modèle de données le suppose déjà.

### 5.1 Chiffrement

- **En transit** : TLS 1.3 obligatoire, HSTS, **certificate pinning** côté Flutter sur le domaine d'API.
- **Au repos, niveau infra** : chiffrement disque de l'instance Postgres managée + SSE sur le bucket objet.
- **Au repos, niveau applicatif (colonnes 🔒)** : *envelope encryption*. Une **KEK** vit dans le gestionnaire de secrets (Scaleway Secret Manager), chiffre une **DEK** par utilisateur, stockée en table `encryption_key`. Chiffrement **AES-256-GCM** via `cryptography`, AAD = `f"{table}:{row_id}:{column}"` pour empêcher le déplacement d'un chiffré d'une ligne à l'autre. Rotation de KEK prévue (re-chiffrement des DEK uniquement, donc bon marché).
  → Conséquence connue et acceptée : ces colonnes ne sont pas triables/filtrables en SQL. Les séries temporelles de poids sont donc déchiffrées et agrégées côté service, sur des volumes qui restent petits (quelques centaines de points par client).
- **Photos de progression** : chiffrées côté serveur **avant** upload objet (clé dérivée de la DEK du client), servies via URL pré-signée à TTL 5 min. Une photo n'est **jamais** visible du coach sans `shared_with_coach = true`.
- **Base locale mobile** : SQLite chiffrée (SQLCipher), clé dans le Keychain/Keystore. Purge complète au logout.

### 5.2 Consentement

- Granulaire et **journalisé** en table `consent` (finalité + version + horodatage + hash d'IP).
- **Bloquant** : à l'onboarding, tant que `tos`, `privacy` et `health_data` ne sont pas accordés, l'API renvoie `403 CONSENT_REQUIRED` sur toute route métier. Le consentement `progress_photos` est séparé et facultatif ; `marketing` est **opt-in décoché par défaut**.
- Révocable à tout moment depuis l'app (écran « Mes données ») ; révoquer `health_data` déclenche le parcours de suppression.
- Mineurs : inscription refusée sous 16 ans au MVP (contrôle sur `birth_date`) — assumé pour éviter la gestion du consentement parental.

### 5.3 Droits des personnes

| Droit | Implémentation |
|---|---|
| Accès / portabilité | `POST /me/data-export` → tâche Celery → archive **ZIP (JSON + médias)** chiffrée, lien pré-signé valable 24 h, notification push. SLA 30 j, cible < 1 h. |
| Effacement | `POST /me/delete-account` → fenêtre de rétractation **7 jours**, puis purge **physique** : lignes supprimées, objets S3 supprimés, DEK détruite (crypto-shredding). Les `billing_event` sont conservés anonymisés (obligation comptable, 10 ans), sans lien vers une personne identifiable. |
| Rectification | Édition en app de toutes les données déclaratives. |
| Opposition / limitation | Bascule « mettre en pause le partage avec mon coach » → passe le lien en `paused`, le coach perd l'accès en lecture. |

### 5.4 Minimisation, localisation, rétention

- **Localisation** : tous les traitements et stockages en UE (Paris). Aucun transfert hors UE de donnée personnelle.
- **Cas des notifications push** : FCM et APNs sont opérés hors UE — c'est inévitable pour du push mobile. Mitigation retenue : **les payloads push sont « data-only » et opaques** (`{"n": "<uuid>"}`), sans nom, sans contenu de message, sans donnée de santé. L'app récupère le contenu réel via l'API authentifiée. Seul le token d'appareil transite. Cette limite est documentée dans la politique de confidentialité. *(Alternative UnifiedPush évaluée : rejetée au MVP, quasi inutilisable sur iOS.)*
- **Logs** : `structlog` JSON, identifiants pseudonymisés, **jamais** de body de requête sur les routes sensibles, rétention 30 j.
- **Rétention** : compte inactif 24 mois → e-mail d'avertissement puis anonymisation. Exports RGPD purgés à 24 h.
- **DPIA** : requise (données de santé + suivi systématique). Trame à créer dans `docs/rgpd/dpia.md` avant la mise en production — pas bloquant pour le MVP en environnement de dev, **bloquant pour le staging avec de vrais utilisateurs**.
- Un **registre des traitements** (`docs/rgpd/registre.md`) est maintenu en parallèle du code.

---

## 6. Bibliothèque d'exercices — décision et justification légale

### Ce que la vérification des licences a donné (2026-09-22)

| Source | Licence réelle | Verdict |
|---|---|---|
| **ExerciseDB** (dépôt libre / API V1 gratuite) | Code **AGPL-3.0** ; dataset gratuit **non-commercial + attribution**. Les droits commerciaux sur les GIF sont vendus séparément (licence payante one-shot via exercisedb.io). | ❌ **Écarté** au MVP. La version gratuite est incompatible avec notre usage commercial. La licence payante reste une **option d'achat ultérieure**, pas une dépendance de départ. |
| **Wger** | Application **AGPL-3.0** ; données d'exercices initiales en **CC-BY-SA 3.0**, avec des licences qui varient **par exercice** pour les images. | ❌ **Écarté** pour le socle. Le *share-alike* obligerait à republier notre catalogue dérivé sous CC-BY-SA, et l'hétérogénéité des licences d'images rend l'audit ingérable. L'AGPL de l'app importerait en plus une obligation de divulgation du code si on en réutilisait le serveur. |
| **yuhonas/free-exercise-db** | **Unlicense** (renonciation au domaine public) — ~873 exercices, instructions, groupes musculaires, équipement, **photos de démonstration incluses**. | ✅ **Retenu comme seed.** Aucune restriction commerciale, aucune obligation d'attribution, aucun share-alike. |
| Banques de vidéos « gratuites » généralistes | Licences le plus souvent *non libres de droit* pour un usage commercial, et souvent révocables. | ❌ **Interdit.** Aucun agent ne doit télécharger de vidéo d'exercice depuis une source tierce. |

### Décision retenue — option (c) + (b) combinées

1. **Catalogue global de démarrage** : seed depuis **free-exercise-db (Unlicense)**. Les images sont **rapatriées dans notre propre bucket UE** (jamais de hotlink GitHub : disponibilité non garantie, et un hotlink expose l'IP de nos utilisateurs à un tiers). Chaque `exercise` seedé porte `media_license = 'public_domain'`, `source = 'seed'`.
2. **Vidéos** : **aucune vidéo tierce**. Chaque coach peut **uploader ses propres vidéos de démonstration** (`source = 'coach'`, `media_license = 'coach_owned'`). Les CGU coach incluent une garantie de détention des droits et une licence d'hébergement/diffusion accordée à CoachLink. Une vidéo uploadée par un coach est par défaut **privée à son périmètre** ; le partage vers le catalogue public est une action explicite et modérée.
3. **Champ `media_license` obligatoire** sur chaque média : il rend l'audit juridique faisable à tout moment et conditionne la visibilité publique.
4. **Porte de sortie assumée** : si la qualité visuelle du domaine public devient un frein commercial, on achète la licence commerciale ExerciseDB ou on produit nos propres médias. L'architecture ne change pas — seule la valeur de `media_license` change. C'est précisément pourquoi ce champ existe dès le MVP.

Contraintes techniques médias : upload direct vers S3 via URL pré-signée (jamais à travers l'API), images ≤ 5 Mo (WebP), vidéos ≤ 100 Mo / 60 s, transcodage en H.264 720p + vignette via worker Celery.

---

## 7. Système d'abonnement extensible

Objectif : rendre la facturation **branchable** sans la câbler au MVP.

### Port / adaptateurs

```python
class BillingProvider(Protocol):
    async def create_customer(self, user: User) -> str: ...
    async def start_trial(self, subject: Subject, days: int) -> Subscription: ...
    async def subscribe(self, subject: Subject, plan: PlanCode) -> Subscription: ...
    async def cancel(self, subscription_id: UUID) -> None: ...
    async def report_usage(self, coach_id: UUID, active_clients: int, period: Period) -> None: ...
    async def handle_webhook(self, payload: bytes, signature: str) -> list[BillingEvent]: ...
```

- **`ManualBillingProvider`** — implémenté au MVP. Gère l'essai de 10 jours et les états d'abonnement **en base, sans encaissement**. Suffit à valider tout le comportement produit (blocage en fin d'essai, réactivation, calcul de commission).
- **`StripeBillingProvider`** — **scaffoldé, non implémenté** : signatures présentes, corps levant `NotImplementedError`, tests marqués `skip`. Stripe est choisi pour son *usage-based billing* et Stripe Tax (TVA UE), avec les données client en région UE.

Le reste de l'application ne connaît **que** le `Protocol`. Changer de prestataire = écrire un adaptateur.

### Règles métier

- **Client** : `trial_ends_at = created_at + 10 jours` à la création du lien coach-client. Après expiration sans abonnement → **mode lecture seule** (consultation du programme en cours et de l'historique, mais plus de log de séance ni de messagerie). On ne coupe jamais l'accès à ses propres données — c'est aussi une exigence RGPD.
- **Coach** : gratuit. Commission mensuelle par **client actif**.
- **Définition de « client actif »** (règle à figer avec le chef de projet, implémentée comme une fonction pure et testable `is_client_active(link, month) -> bool`) : lien `active` **et** au moins une séance loguée **ou** une mesure enregistrée **ou** un message échangé sur le mois civil. Un job Celery mensuel matérialise `active_client_snapshot` → idempotent, rejouable, auditable.
- **Webhooks** : endpoint `/webhooks/billing` avec vérification de signature et **idempotence** par `provider_event_id`.

### Risque à remonter au chef de projet

Apple (App Store 3.1.1) et Google imposent leur **achat in-app** pour un abonnement déverrouillant du contenu numérique dans l'app, avec une commission de 15–30 %, ce qui est incompatible avec un paiement Stripe *dans* l'app. Options : (a) IAP mobile via RevenueCat + Stripe pour le web, (b) souscription hors app (« reader-like »), (c) facturer le coach hors app plutôt que le client. **Décision produit requise avant l'implémentation du paiement réel** — sans impact sur le MVP puisque seul `ManualBillingProvider` est actif.

---

## 8. Conventions d'API

- Base : `/api/v1`, JSON, `snake_case`, dates **ISO-8601 UTC**.
- Erreurs normalisées : `{"error": {"code": "CONSENT_REQUIRED", "message": "...", "details": {...}}}`.
- Pagination **cursor-based** : `?cursor=…&limit=…` → `{"items": [...], "next_cursor": "..."}`.
- Idempotence : header `Idempotency-Key` sur `POST /workout-logs` et toute route de facturation (indispensable pour rejouer la file offline).
- Sync offline : `GET /sync?since=<timestamp>` renvoie les deltas ; résolution de conflit **last-write-wins par champ**, sauf `set_log` où **le client fait toujours foi** (c'est lui qui était à la salle).
- WebSocket `/ws` authentifié par JWT ; canaux `user:{id}` et `link:{id}`. Événements : `program.published`, `workout.completed`, `message.created`, `measurement.created`.
- Rate limiting : 100 req/min par utilisateur, 5 tentatives/min sur `/auth/login`.
- OpenAPI exposé en dev → génération des modèles Dart.

---

## 9. Ce qui est explicitement HORS périmètre MVP

Pour éviter la dérive : pas de paiement réel encaissé, pas de visio, pas de wearables (Apple Health / Google Fit), pas de web app coach, pas d'IA de génération de programme, pas de multi-langue au-delà du FR, pas de marketplace publique de coachs.

---

## 10. Registre des décisions d'architecture (ADR courts)

| ID | Date | Décision | Justification condensée |
|---|---|---|---|
| ADR-001 | 2026-09-22 | Flutter pour le mobile | Cross-platform natif (C1) + familiarité équipe |
| ADR-002 | 2026-09-22 | FastAPI / Python 3.12 | Familiarité, contrat OpenAPI, WebSocket natif |
| ADR-003 | 2026-09-22 | PostgreSQL plutôt que MongoDB | Domaine relationnel, RLS, intégrité pour la facturation |
| ADR-004 | 2026-09-22 | Mono-repo | Équipe réduite, contrat d'API partagé |
| ADR-005 | 2026-09-22 | Hébergement Scaleway Paris | Souveraineté UE, coût, S3-compatible |
| ADR-006 | 2026-09-22 | Envelope encryption AES-256-GCM par utilisateur | Données de santé, crypto-shredding à la suppression |
| ADR-007 | 2026-09-22 | Catalogue seed free-exercise-db (Unlicense) + upload vidéo coach | Seule source vérifiée sans restriction commerciale ; ExerciseDB gratuit non-commercial et Wger CC-BY-SA écartés |
| ADR-008 | 2026-09-22 | `BillingProvider` port + `ManualBillingProvider` au MVP | Facturation branchable sans câbler Stripe |
| ADR-009 | 2026-09-22 | Push data-only sans PII via FCM/APNs | Seule option viable sur iOS ; minimisation stricte du payload |
| ADR-010 | 2026-09-22 | Offline-first Drift/SQLCipher + `/sync` | Usage en salle, réseau instable (C6) |
