# CoachLink

Application mobile mettant en relation un coach sportif et ses clients : gestion de programmes
d'entraînement, suivi de progression (poids, mensurations, photos, performances), plans
alimentaires optionnels, messagerie coach-client, et abonnement (essai gratuit 10 jours,
commission par client actif).

## État du projet

Le projet est en phase de cadrage. La stack technique (mobile / backend / base de données) est en
cours de décision par le Tech Lead et sera documentée dans [`ARCHITECTURE.md`](./ARCHITECTURE.md)
dès qu'elle sera tranchée. Cette section (et "Lancer le projet en dev" ci-dessous) sera mise à jour
en conséquence.

Le backlog partagé de l'équipe (par phase et par agent) est dans [`TASKS.md`](./TASKS.md).

## Contraintes clés

- **RGPD dès la conception** : chiffrement au repos/transit, hébergement UE, consentement
  explicite, export/suppression des données utilisateur — non négociable.
- **Abonnement extensible** : essai gratuit 10 jours côté client, commission par client actif côté
  coach (scaffolding paiement, ex. Stripe).

## Structure du repo

_À confirmer une fois la stack tranchée (mono-repo probable vu la synchronisation temps réel
coach-client). Structure indicative pressentie :_

```
CoachLink/
├── mobile/           # application mobile (coach + client)
├── backend/          # API + logique métier
├── docs/             # documentation technique complémentaire
├── ARCHITECTURE.md   # décisions stack, modèle de données, RGPD (Tech Lead)
├── TASKS.md          # backlog partagé de l'équipe
└── README.md
```

## Lancer le projet en dev

_À compléter dès que la stack est choisie et qu'un premier environnement de dev/staging est en
place (voir Phase 1/5 dans TASKS.md)._

## Équipe

Projet construit par une équipe multi-agents : chef de projet, tech lead, back, front (mobile),
QA, devops.
