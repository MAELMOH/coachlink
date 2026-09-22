# Documentation CoachLink

Ce dossier accueille la documentation qui n'a pas sa place dans `ARCHITECTURE.md` (qui reste le
document de référence technique, maintenu par le Tech Lead).

## Organisation

| Dossier | Contenu | Responsable |
|---|---|---|
| `adr/` | Architecture Decision Records détaillés. Le registre condensé vit dans `ARCHITECTURE.md` §10 ; ce dossier accueille les ADR qui méritent un développement long. | Tech Lead |
| `rgpd/` | Conformité : registre des traitements, DPIA, politique de confidentialité. | Tech Lead / juridique |
| `deploiement/` | Procédures de déploiement, runbooks, configuration des environnements. | DevOps |

## Documents attendus avant la mise en production

Ces documents ne sont **pas** bloquants pour le MVP en environnement de développement, mais le
sont pour un staging exposé à de vrais utilisateurs (voir `ARCHITECTURE.md` §5.4) :

- `rgpd/registre.md` — registre des traitements, maintenu en parallèle du code.
- `rgpd/dpia.md` — analyse d'impact, **requise** ici (données de santé + suivi systématique).
- `deploiement/runbook.md` — procédure de déploiement et de rollback.
