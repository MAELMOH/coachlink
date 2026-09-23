#!/usr/bin/env python3
"""Échoue si les tests adossés à PostgreSQL n'ont pas RÉELLEMENT tourné.

Mode d'échec visé (signalé par `back`, 2026-09-23)
--------------------------------------------------
`tests/support/database.py` skippe volontairement les tests `integration` et `rls`
quand aucun PostgreSQL n'est joignable, plutôt que de retomber sur SQLite — un choix
correct, puisque les policies RLS n'existent pas en SQLite et qu'une suite verte sur
SQLite ne prouverait rien de la barrière n°1 du projet (ARCHITECTURE.md §4).

Mais ce skip est *silencieux du point de vue du code de sortie* : pytest renvoie 0.
Une CI où `TEST_DATABASE_URL` serait mal nommée, où le service container n'aurait pas
démarré, ou — cas réellement observé en local — où les extras `dev`
(`testcontainers`, `psycopg`) ne seraient pas installés, afficherait donc une suite
« verte » qui n'a vérifié aucune isolation. C'est strictement pire que rouge : ça
donne une confiance injustifiée dans la garantie la plus critique du produit.

Ce script relit le rapport JUnit produit par pytest et exige que, pour chaque
répertoire surveillé, au moins un test ait tourné et qu'aucun n'ait été skippé.

xfail ≠ skip
------------
pytest écrit **les deux** dans la balise ``<skipped>``, et seul l'attribut ``type``
les distingue (vérifié avec la version de pytest du projet, 2026-09-23) :

* ``type="pytest.skip"``  → le test n'a pas tourné. C'est le cas qu'on traque.
* ``type="pytest.xfail"`` → le test a tourné et a échoué comme prévu, parce que le
  code n'est pas encore écrit. C'est la méthode *spec-first* de la QA
  (``tests/support/pending.py``) : le test devient un vrai test, automatiquement, dès
  que le symbole existe — sans marqueur à retirer à la main, donc sans risque de
  marqueur périmé avalant une vraie régression.

Traiter un xfail comme un skip rendrait ce garde rouge en permanence jusqu'à la fin de
la phase 2 et reviendrait à interdire à la QA d'écrire ses tests en avance, qui est
précisément la méthode retenue. Les xfail sont donc tolérés — mais comptés et affichés,
pour qu'un groupe entièrement xfail reste visible dans le log.

Usage : python .github/scripts/assert_db_tests_ran.py backend/reports/pytest.xml
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

#: Répertoires dont les tests DOIVENT s'exécuter en CI (jamais être skippés).
WATCHED = ("tests/rls", "tests/integration")


def _group_of(testcase: ET.Element) -> str | None:
    """Rattache un <testcase> à l'un des répertoires surveillés, ou None."""
    # pytest renseigne file="tests/rls/test_x.py" et classname="tests.rls.test_x".
    # On accepte les deux : le format exact varie selon la version et le rootdir.
    candidates = (testcase.get("file") or "", testcase.get("classname") or "")
    for watched in WATCHED:
        dotted = watched.replace("/", ".")
        for candidate in candidates:
            normalised = candidate.replace("\\", "/")
            if normalised.startswith(watched) or candidate.startswith(dotted):
                return watched
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <rapport-junit.xml>", file=sys.stderr)
        return 2

    report = Path(argv[1])
    if not report.is_file():
        print(f"::error::Rapport JUnit introuvable : {report}. La suite pytest a-t-elle tourné ?")
        return 1

    root = ET.parse(report).getroot()

    ran: dict[str, int] = {w: 0 for w in WATCHED}
    skipped: dict[str, list[str]] = {w: [] for w in WATCHED}
    xfailed: dict[str, int] = {w: 0 for w in WATCHED}

    for testcase in root.iter("testcase"):
        group = _group_of(testcase)
        if group is None:
            continue
        skip_node = testcase.find("skipped")
        if skip_node is None:
            ran[group] += 1
        elif skip_node.get("type") == "pytest.xfail":
            # Fonctionnalité pas encore écrite, déclarée comme telle. Toléré.
            xfailed[group] += 1
        else:
            reason = skip_node.get("message") or skip_node.text or "(sans raison)"
            name = testcase.get("name") or "(anonyme)"
            skipped[group].append(f"{name} — {reason.strip()}")

    failed = False
    for watched in WATCHED:
        suffix = f", {xfailed[watched]} xfail (pas encore implémenté)" if xfailed[watched] else ""

        if skipped[watched]:
            failed = True
            print(
                f"::error::{len(skipped[watched])} test(s) de {watched}/ ont été SKIPPÉS en CI "
                "(skip franc, pas xfail). Ces tests doivent tourner : ils vérifient l'isolation "
                "entre coachs (ARCHITECTURE.md §4). Une suite verte avec ces tests skippés ne "
                "prouve rien. Cause la plus fréquente : PostgreSQL injoignable, ou extras `dev` "
                "non installés."
            )
            for line in skipped[watched][:10]:
                print(f"  - {line}")
            if len(skipped[watched]) > 10:
                print(f"  … et {len(skipped[watched]) - 10} autre(s).")
        elif ran[watched] == 0 and xfailed[watched] == 0:
            failed = True
            print(
                f"::error::AUCUN test n'a été exécuté dans {watched}/. "
                "Soit la collecte est cassée, soit le répertoire a été vidé — "
                "dans les deux cas la CI ne vérifie plus ce qu'elle prétend vérifier."
            )
        elif ran[watched] == 0:
            # Tout le groupe est en attente d'implémentation : légitime en phase
            # précoce, mais la CI ne vérifie alors rien ici — on le dit fort sans
            # bloquer, sinon on interdirait à la QA d'écrire ses tests en avance.
            print(
                f"::warning::Aucun test réellement exécuté dans {watched}/ : "
                f"les {xfailed[watched]} test(s) du groupe sont tous en xfail "
                "(code pas encore écrit). Aucune garantie n'est vérifiée ici pour l'instant."
            )
        else:
            print(f"OK — {ran[watched]} test(s) exécuté(s) dans {watched}/, aucun skip franc{suffix}.")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
