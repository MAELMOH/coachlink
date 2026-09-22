# CoachLink — Backlog partagé

Liste de travail partagée de l'équipe multi-agents. Chaque teammate coche/complète ses tâches
et peut ajouter des sous-tâches dans sa section. Ne pas supprimer les tâches des autres — marquer
`[x]` fait, `[~]` en cours, `[ ]` à faire, `[!]` bloqué (préciser pourquoi).

Statut Jira : indisponible pour le moment (politique de sécurité IP côté organisation Atlassian
`coachlink.atlassian.net` — à débloquer par l'admin org si souhaité). On reste sur ce fichier.

---

## Phase 0 — Cadrage & architecture (bloquant pour les phases 2-4)

- [ ] **[Chef de projet]** Spécifications fonctionnelles détaillées (user stories coach/client,
      règles métier : essai gratuit 10j, présentiel vs distance, commission par client actif)
- [ ] **[Tech Lead]** Choix stack mobile + backend + DB → documenté dans `ARCHITECTURE.md`
- [ ] **[Tech Lead]** Décision bibliothèque d'exercices (API ouverte type ExerciseDB/Wger vs
      upload par coach vs bibliothèque restreinte de démarrage) — documentée et justifiée
- [ ] **[Tech Lead]** Modèle de données initial (coach, client, lien coach-client, programme,
      exercice, séance, série, mensuration, photo, plan alimentaire, repas, message, abonnement)
- [ ] **[Tech Lead]** Stratégie RGPD dès la conception (chiffrement repos/transit, hébergement UE,
      consentement explicite, export/suppression des données) — non négociable, pas en bonus
- [ ] **[Tech Lead]** Design du système d'abonnement extensible (essai 10j client, commission
      coach/client actif) — scaffolding Stripe ou équivalent, sans forcément l'implémenter en MVP
- [ ] **[Tech Lead]** Recruter les teammates Front (mobile), Back, QA une fois la stack tranchée

## Phase 1 — Fondations (DevOps, démarre en parallèle de la phase 0)

- [~] Créer le repo GitHub (ou init local si pas encore de remote), structure de base, README
      — repo git local initialisé + README + .gitignore en place. Reste : structure finale
      (mono-repo /mobile /backend) une fois ARCHITECTURE.md dispo, puis remote GitHub (attend
      confirmation explicite utilisateur avant tout push/création de repo distant).
- [ ] Pipeline CI basique (lint + tests) dès que du code existe — bloqué sur stack (tech-lead) et
      sur premier code (back/front)
- [ ] Environnement dev/staging (hébergement UE pour conformité RGPD) — bloqué sur stack

## Phase 2 — Backend (Agent Back, débloqué après Phase 0)

- [ ] Auth coach/client + invitation par code/lien
- [ ] API Programmes (exercices, séries, reps, charge, temps de repos)
- [ ] API Bibliothèque d'exercices (images/vidéos selon décision Tech Lead)
- [ ] API Suivi client (poids, mensurations, photos, performances, séances réalisées)
- [ ] API Plans alimentaires (optionnel par coach : calories, macros, repas types)
- [ ] API Messagerie (mode coaching à distance)
- [ ] Calcul automatique du volume d'entraînement (séries × reps × charge)
- [ ] Notifications/rappels de séance
- [ ] Endpoints RGPD (consentement, export, suppression des données)
- [ ] Scaffolding paiement (Stripe : essai 10j, commission par client actif)

## Phase 3 — Mobile Front (Agent Front, débloqué après Phase 0)

- [ ] Écrans coach : dashboard multi-clients, création programme, bibliothèque d'exercices,
      suivi client, invitation client, plans alimentaires (option), messagerie
- [ ] Écrans client : programme du jour/semaine, cocher séries/reps/charge, média d'exécution
      des exercices, plan alimentaire, graphiques de progression, messagerie
- [ ] Onboarding + consentement RGPD explicite + essai gratuit 10 jours
- [ ] Notifications push

## Phase 4 — QA (Agent Testeur, en continu dès que du code existe, pas juste à la fin)

- [ ] Tests unitaires backend au fil de l'eau
- [ ] Tests unitaires front au fil de l'eau
- [ ] Tests d'intégration API
- [ ] Tests end-to-end des parcours critiques (invitation coach-client, création/complétion de
      séance, suivi de progression)
- [ ] Vérification RGPD (chiffrement effectif, consentement bloquant, export/suppression)

## Phase 5 — Déploiement (DevOps)

- [ ] Environnement staging fonctionnel et accessible
- [ ] Documentation de déploiement

---

## Journal des décisions

_(Tech Lead / chaque agent : consigner ici les décisions importantes avec la date et la justification)_

- **2026-09-22 [DevOps]** Repo git initialisé en local (`git init`, branche `main`), README.md et
  .gitignore génériques créés. Pas de remote GitHub créé/connecté pour l'instant — en attente
  d'un remote existant fourni par l'utilisateur ou d'une confirmation explicite avant d'en créer
  un (action visible publiquement, hors périmètre d'auto-décision DevOps). Structure interne du
  repo (mono-repo /mobile /backend pressenti) volontairement pas encore créée : en attente
  d'ARCHITECTURE.md du Tech Lead pour ne pas imposer une arborescence qui ne correspondrait pas à
  la stack retenue. Coordination lancée avec tech-lead (SendMessage) pour être notifié dès que
  ARCHITECTURE.md est prêt et dès que back/front/QA sont recrutés (pour caler le pipeline CI).
