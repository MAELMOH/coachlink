## Quoi / Pourquoi

<!-- Que change cette PR, et pour quelle raison ? Lier la tâche de TASKS.md. -->

## Comment tester

<!-- Étapes concrètes pour vérifier le comportement. -->

## Checklist

- [ ] Le titre suit les [Conventional Commits](https://www.conventionalcommits.org/) (`feat(backend): …`)
- [ ] CI verte (lint, types, tests)
- [ ] Pas de secret ni de donnée personnelle réelle ajoutés au dépôt

### Si la PR touche aux données client

- [ ] Les nouvelles tables portant des données client déclarent `ENABLE` **et** `FORCE ROW LEVEL SECURITY`
- [ ] Les colonnes sensibles (🔒 dans `ARCHITECTURE.md` §4) sont chiffrées applicativement
- [ ] L'accès coach → données client passe par un `coach_client_link` en statut `active`
- [ ] Les accès aux données sensibles sont tracés dans `audit_log`
- [ ] Aucune donnée personnelle dans les logs ni dans les payloads de notification push
