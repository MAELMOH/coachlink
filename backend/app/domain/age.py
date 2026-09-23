"""Age rules (ARCHITECTURE.md §5.2).

    « Mineurs : inscription refusée sous 16 ans au MVP (contrôle sur ``birth_date``) —
    assumé pour éviter la gestion du consentement parental. »

Pure and date-only, so the rule can be tested without a clock, a database or a request.
"""

from __future__ import annotations

from datetime import date

__all__ = ["age_on", "is_old_enough"]


def age_on(birth_date: date, reference: date) -> int:
    """Completed years between ``birth_date`` and ``reference``.

    The ``(month, day)`` comparison is what makes a birthday later in the year count as
    *not yet reached*. Naive year subtraction would let a 15-year-old born in December
    register in January.
    """
    years = reference.year - birth_date.year
    if (reference.month, reference.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def is_old_enough(birth_date: date, reference: date, minimum_age: int) -> bool:
    return age_on(birth_date, reference) >= minimum_age
