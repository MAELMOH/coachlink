# CoachLink — Spécifications fonctionnelles

> Document de référence produit. Auteur : Chef de projet. Dernière mise à jour : **2026-09-23**.
> Complète `ARCHITECTURE.md` (qui décrit le *comment*) : ce document décrit le *quoi* et le *pourquoi*
> côté utilisateur. Toute story ci-dessous doit rester cohérente avec le modèle de données
> d'`ARCHITECTURE.md` §4 — en cas d'écart, la story prime pour le besoin, l'architecture prime pour
> la faisabilité technique ; on se coordonne avec le Tech Lead avant de trancher.

---

## 1. Personas

- **Coach** — professionnel indépendant ou petite structure, gère plusieurs clients, en présentiel
  et/ou à distance. Objectif : gagner du temps sur le suivi administratif, garder une vue d'ensemble,
  fidéliser ses clients. Compétence numérique variable — l'app doit rester simple.
- **Client** — pratiquant encadré par un coach, utilise l'app en salle (réseau instable) ou chez lui.
  Objectif : savoir quoi faire aujourd'hui sans avoir à demander, suivre sa progression, garder le
  contact avec son coach sans effort.

---

## 2. Règles métier transverses

Ces règles s'appliquent à toutes les stories ci-dessous ; elles ne sont pas répétées à chaque fois.

### 2.1 Mode de coaching : présentiel vs distance

Chaque lien coach-client porte un `coaching_mode` (`ARCHITECTURE.md` §4) fixé à la création du lien,
modifiable ensuite par le coach.

| | Présentiel | Distance |
|---|---|---|
| Programme poussé au client | Oui | Oui |
| Séance à cocher côté client | Optionnel — le coach peut suivre "à l'œil" en salle | Attendu — c'est la seule source de suivi |
| Messagerie | **Désactivée** | **Activée** |
| Suivi mesures/photos | Oui, les deux modes | Oui, les deux modes |

*Pourquoi cette distinction* : en présentiel le coach est physiquement présent pendant la séance,
lui imposer une double saisie (papier/oral + app) serait un frein à l'adoption. À distance, l'app
*est* le seul canal de suivi — elle doit donc être complète.

### 2.2 Essai gratuit client (10 jours)

- Démarre à la création du `coach_client_link` (acceptation de l'invitation), pas à l'inscription
  du compte — un client peut créer un compte avant d'être lié à un coach sans consommer son essai.
- Pendant l'essai : accès complet à toutes les fonctionnalités client.
- À l'expiration sans abonnement actif : **mode lecture seule** — consultation du programme en
  cours et de l'historique, mais impossible de loguer une nouvelle séance ou d'envoyer un message.
  On ne coupe jamais l'accès aux données déjà produites (exigence RGPD autant que produit : un
  client qui a payé pour un mois de suivi doit pouvoir le consulter après).
- Le client voit un bandeau de compte à rebours dès **J-3**, puis un écran de fin d'essai explicite
  à l'expiration (pas juste des boutons grisés sans explication).

### 2.3 Modèle économique coach : commission par client actif

- Le coach n'a **jamais** de plafond de clients ni de mur payant sur les fonctionnalités.
- Une commission est due par client dans l'état **« actif »** sur le mois civil écoulé.
- **Définition de « client actif » — TRANCHÉE le 2026-09-23** (chef de projet, cf. ADR-011 dans
  `ARCHITECTURE.md` §10 et détail §7). Un client est actif un mois civil donné si, cumulativement :
  1. son lien coach-client est `active` ce mois-là ;
  2. ce n'est **pas** le mois de création du lien — pas de prorata, l'éligibilité démarre le mois
     suivant ;
  3. il n'est **pas** en période d'essai gratuit — un client en essai ne génère jamais de commission ;
  4. il cumule **au moins 2 événements qualifiants** sur le mois (séance loguée `completed`, mesure
     enregistrée, message envoyé — combinaison libre).
- Le coach voit dans son dashboard un récapitulatif mensuel : nombre de clients actifs, montant de
  commission estimé/facturé, historique des factures (une fois `StripeBillingProvider` implémenté —
  hors MVP, cf. `ARCHITECTURE.md` §7).

### 2.4 Consentement RGPD (rappel produit)

Aucune fonctionnalité métier n'est utilisable tant que les consentements obligatoires (CGU,
confidentialité, données de santé) n'ont pas été donnés à l'onboarding — voir `ARCHITECTURE.md` §5.2
pour le détail technique. Les stories ci-dessous supposent ce gate déjà passé.

---

## 3. User stories — Coach

### 3.1 Onboarding & gestion de compte

- **US-C01** — En tant que coach, je veux créer un compte et choisir mon mode de coaching par
  défaut (présentiel/distance), afin de configurer rapidement mes futurs liens clients.
  - *Critères* : inscription email + mot de passe ; choix du mode par défaut modifiable plus tard
    par lien ; passage obligatoire par l'écran de consentement RGPD avant tout accès aux
    fonctionnalités.
- **US-C02** — En tant que coach, je veux indiquer si je propose des plans alimentaires, afin que
  cette fonctionnalité n'encombre pas l'interface si je ne l'utilise pas.
  - *Critères* : bascule `offers_nutrition` dans mon profil ; si désactivée, aucun écran nutrition
    n'apparaît ni côté coach ni côté client lié.

### 3.2 Gestion des clients

- **US-C03** — En tant que coach, je veux générer un code ou un lien d'invitation, afin qu'un
  client puisse rejoindre mon suivi sans que j'aie à connaître son mot de passe ou créer son compte
  à sa place.
  - *Critères* : code à 8 caractères lisible (pas de 0/O, 1/l ambigus) + lien profond ; expiration
    configurable ; je choisis le mode (présentiel/distance) au moment de l'invitation ; je vois la
    liste de mes invitations en attente et peux les révoquer.
- **US-C04** — En tant que coach, je veux voir en un coup d'œil l'état de tous mes clients, afin de
  savoir qui a besoin d'attention sans ouvrir chaque fiche une par une.
  - *Critères* : dashboard listant chaque client actif avec dernière séance réalisée, statut
    d'essai/abonnement, et une alerte visuelle si inactif depuis plus de X jours (seuil à définir en
    phase de design, pas bloquant pour le MVP).
- **US-C05** — En tant que coach, je veux mettre en pause ou révoquer le lien avec un client, afin
  de gérer une interruption temporaire ou une fin de collaboration sans supprimer son historique.
  - *Critères* : `paused` = le client garde l'accès à ses propres données mais je perds l'accès en
    lecture à ses données sensibles ; `revoked` = fin définitive, historique conservé côté client.

### 3.3 Programmes & bibliothèque d'exercices

- **US-C06** — En tant que coach, je veux construire un programme avec des séances, des exercices,
  des séries/répétitions/charge/repos, afin de définir précisément le travail attendu de mon client.
  - *Critères* : un programme peut être un modèle réutilisable (non lié à un client précis) puis
    dupliqué et assigné ; état `draft` tant qu'il n'est pas publié — le client ne voit rien avant
    publication explicite.
- **US-C07** — En tant que coach, je veux chercher un exercice dans une bibliothèque avec image (et
  vidéo si disponible), afin de construire un programme sans tout ressaisir de zéro.
  - *Critères* : recherche par nom, filtre par muscle/équipement ; catalogue de base fourni au
    lancement (cf. `ARCHITECTURE.md` §6 pour l'origine et la licence des médias).
- **US-C08** — En tant que coach, je veux créer mon propre exercice avec ma propre vidéo de
  démonstration, afin de couvrir un mouvement spécifique à ma méthode qui n'est pas dans le
  catalogue de base.
  - *Critères* : upload image/vidéo avec limites de taille annoncées avant l'envoi (pas après
    échec) ; l'exercice créé est privé à mon périmètre par défaut, le partage au catalogue public
    est une action explicite.

### 3.4 Suivi client

- **US-C09** — En tant que coach, je veux consulter l'historique complet des séances d'un client
  (réalisées, séries, charges), afin d'ajuster son programme en connaissance de cause.
- **US-C10** — En tant que coach, je veux voir les mensurations et le poids déclarés par mon
  client sous forme de graphique, afin de repérer une tendance sans faire le calcul moi-même.
- **US-C11** — En tant que coach, je veux voir les photos de progression que mon client a choisi de
  partager avec moi, afin d'évaluer visuellement son évolution.
  - *Critères* : **jamais** de photo visible sans que le client ait explicitement activé le partage
    pour cette photo précise (opt-in par photo, pas un interrupteur global qui partagerait
    rétroactivement l'historique).

### 3.5 Plans alimentaires (si activés)

- **US-C12** — En tant que coach ayant activé la nutrition, je veux créer un plan alimentaire avec
  des repas types (calories, macros), afin de compléter mon accompagnement sportif.
- **US-C13** — En tant que coach, je veux voir si mon client suit son plan alimentaire, afin
  d'adapter mes conseils.

### 3.6 Messagerie (mode distance uniquement)

- **US-C14** — En tant que coach en mode distance, je veux échanger des messages avec mon client
  depuis l'app, afin de répondre à ses questions sans passer par un autre canal.
  - *Critères* : messagerie absente/masquée si le lien est en mode présentiel (§2.1).

---

## 4. User stories — Client

### 4.1 Onboarding & compte

- **US-U01** — En tant que client, je veux créer un compte et rejoindre mon coach via un code ou un
  lien, afin de démarrer mon suivi sans démarche administrative.
  - *Critères* : passage obligatoire par le consentement RGPD avant tout accès ; si j'utilise un
    lien d'invitation avant même d'avoir un compte, je suis redirigé vers l'inscription puis
    reconduit automatiquement vers l'acceptation de l'invitation (le lien n'est pas perdu en route).
- **US-U02** — En tant que client, je veux savoir combien de jours il me reste sur mon essai
  gratuit, afin de ne pas être surpris par la bascule en lecture seule.
  - *Critères* : bandeau visible dès J-3 (§2.2) ; écran dédié et explicite à l'expiration, pas un
    simple blocage silencieux.

### 4.2 Programme & exécution

- **US-U03** — En tant que client, je veux voir mon programme du jour (ou de la semaine), afin de
  savoir précisément quoi faire sans avoir à redemander à mon coach.
- **US-U04** — En tant que client, je veux cocher chaque série effectuée et indiquer la charge
  utilisée pendant ma séance, afin de garder une trace fidèle sans avoir à m'en souvenir plus tard.
  - *Critères* : fonctionne **hors ligne** (réseau de salle instable) et se synchronise ensuite ;
    en cas de rejeu (perte réseau puis reconnexion), la séance n'est jamais dupliquée
    (idempotence — cf. `ARCHITECTURE.md` §8).
- **US-U05** — En tant que client, je veux voir l'image ou la vidéo de bonne exécution d'un
  exercice pendant ma séance, afin d'éviter une erreur de forme sans que mon coach soit présent.
- **US-U06** — En tant que client, je veux consulter l'historique complet de mes séances passées,
  afin de constater mes progrès ou revoir ce que j'ai fait la semaine dernière.

### 4.3 Suivi personnel

- **US-U07** — En tant que client, je veux enregistrer mon poids et mes mensurations, afin de
  suivre mon évolution dans le temps.
- **US-U08** — En tant que client, je veux ajouter une photo de progression et **choisir** si elle
  est visible par mon coach, afin de garder le contrôle sur une donnée que je juge sensible.
  - *Critères* : non partagé par défaut (§3.4, US-C11) ; je peux révoquer le partage d'une photo
    déjà envoyée.
- **US-U09** — En tant que client, je veux visualiser des graphiques de ma progression (poids,
  charges soulevées, volume d'entraînement), afin de rester motivé en voyant une tendance concrète.

### 4.4 Nutrition (si le coach l'a activée)

- **US-U10** — En tant que client, je veux consulter le plan alimentaire du jour que mon coach m'a
  préparé, afin de savoir quoi manger sans avoir à improviser.
- **US-U11** — En tant que client, je veux cocher les repas que j'ai suivis, afin que mon coach
  voie mon adhérence au plan.

### 4.5 Messagerie (mode distance uniquement)

- **US-U12** — En tant que client en mode distance, je veux écrire à mon coach depuis l'app, afin
  de poser une question sans chercher un autre moyen de contact.

### 4.6 Mes données (RGPD)

- **US-U13** — En tant que client, je veux consulter, exporter ou supprimer mes données depuis un
  écran dédié, afin d'exercer mes droits sans avoir à contacter le support.
  - *Critères* : cf. `ARCHITECTURE.md` §5.3 pour le détail technique (export ZIP, délai de
    rétractation de 7 j avant suppression physique).

---

## 5. Parcours critiques (base du plan de test QA)

Ces parcours bout-en-bout doivent fonctionner avant toute mise en avant du produit — ils recoupent
la liste de tests e2e déjà présente dans `TASKS.md` Phase 4, donnée ici comme référence produit :

1. **Invitation → lien actif** : coach génère un code → client s'inscrit (ou est déjà inscrit) →
   accepte l'invitation → lien `active` créé avec le bon `coaching_mode`.
2. **Programme → séance complétée hors ligne → synchronisation → visible côté coach** : coach
   publie un programme → client le reçoit → complète une séance en coupant le réseau → reconnexion
   → séance visible côté coach avec le bon volume calculé.
3. **Essai → expiration → lecture seule** : lien créé → 10 jours passés sans abonnement → client ne
   peut plus loguer de séance ni écrire de message, mais consulte toujours son historique.
4. **Consentement bloquant** : compte créé sans consentement santé accordé → toute route métier
   renvoie une erreur explicite tant que le consentement manque.
5. **Isolation coach A / client de coach B** : coach A ne doit jamais, ni via l'API ni via un accès
   direct, lire une donnée d'un client qui n'est pas le sien — priorité 1 (cf. `ARCHITECTURE.md` §4
   « Règle d'accès transversale »).
6. **Photo de progression** : photo ajoutée par le client → invisible du coach tant que
   `shared_with_coach` n'est pas explicitement activé pour cette photo.
7. **Présentiel vs distance** : changer le mode d'un lien fait apparaître/disparaître la messagerie
   des deux côtés sans redémarrage de l'app.

---

## 6. Hors périmètre MVP

Voir `ARCHITECTURE.md` §9 (pas de paiement réel encaissé, pas de visio, pas de wearables, pas de
web app coach, pas d'IA de génération de programme, pas de multi-langue au-delà du FR, pas de
marketplace publique de coachs). Ce document produit ne rajoute rien à cette liste ; toute nouvelle
idée de fonctionnalité pendant le développement doit être proposée au chef de projet plutôt
qu'ajoutée directement par un agent.

---

## 7. Décisions produit encore ouvertes

1. ~~Définition précise de « client actif »~~ — **tranchée le 2026-09-23**, voir §2.3 (SCRUM-1 fermé).
2. **Stripe vs achat in-app Apple/Google** pour l'abonnement réel — voir `ARCHITECTURE.md` §7
   « Risque à remonter au chef de projet » (SCRUM-2, toujours ouvert). Sans impact sur le MVP
   (`ManualBillingProvider` actif), mais bloquant avant tout encaissement réel.
