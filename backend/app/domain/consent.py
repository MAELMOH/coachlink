"""Consent rules as pure functions (ARCHITECTURE.md §5.2).

No I/O here on purpose: "which consents are missing" is a legal question with a
precise answer, and it must be testable without a database, a request or a user
object. The dependency that returns ``403 CONSENT_REQUIRED`` is a thin wrapper
around :func:`missing_mandatory_consents`.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.domain.enums import REQUIRED_CONSENTS, ConsentPurpose

__all__ = [
    "has_all_mandatory_consents",
    "is_mandatory",
    "missing_mandatory_consents",
    "normalise_purposes",
]


def normalise_purposes(granted: Iterable[ConsentPurpose | str]) -> frozenset[ConsentPurpose]:
    """Accept enum members or raw strings; drop anything unknown.

    Consent rows are written over months and the vocabulary may grow. An unknown
    purpose read back from the database must never crash the gate — but it must
    never *satisfy* it either, so it is dropped rather than trusted.
    """
    purposes: set[ConsentPurpose] = set()
    for value in granted:
        try:
            purposes.add(ConsentPurpose(value))
        except ValueError:
            continue
    return frozenset(purposes)


def missing_mandatory_consents(
    granted: Iterable[ConsentPurpose | str],
) -> frozenset[ConsentPurpose]:
    """The mandatory purposes still to be granted. Empty means the gate opens."""
    return frozenset(REQUIRED_CONSENTS - normalise_purposes(granted))


def has_all_mandatory_consents(granted: Iterable[ConsentPurpose | str]) -> bool:
    return not missing_mandatory_consents(granted)


def is_mandatory(purpose: ConsentPurpose | str) -> bool:
    """``progress_photos`` and ``marketing`` are opt-in and must never gate the app.

    Gating the product on ``marketing`` in particular would be consent obtained under
    duress, which under the GDPR is not consent at all.
    """
    try:
        value = ConsentPurpose(purpose)
    except ValueError:
        return False
    return value in REQUIRED_CONSENTS
