"""Training volume — ``Σ(reps_done × load_kg)`` (ARCHITECTURE.md §4).

Spec-first: written before ``app/domain/volume.py`` exists. While the module is missing
these report ``xfail``; the moment it lands they run for real (see
``tests/support/pending.py`` for why we do not use a stale ``@xfail`` decorator).

The function is fed **duck-typed** set entries — anything exposing ``reps_done``,
``load_kg`` and ``is_completed``. That keeps the pure domain free of SQLAlchemy while
letting the service pass ``set_log`` rows straight in.

Volume is the number the client sees on their progress chart and the number the coach
judges progression by. Every edge case below is a real gym situation, not a contrived one.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

from tests.support.pending import require


@dataclass(frozen=True)
class SetEntry:
    """Stand-in for a ``set_log`` row (ARCHITECTURE.md §4)."""

    reps_done: int | None = 0
    load_kg: Decimal | None = Decimal("0")
    is_completed: bool = True


def volume_of(*sets: SetEntry) -> Decimal:
    compute_volume = require("app.domain.volume", "compute_volume")
    return compute_volume(sets)


class TestNominal:
    def test_single_set(self) -> None:
        assert volume_of(SetEntry(reps_done=10, load_kg=Decimal("60"))) == Decimal("600")

    def test_sums_across_sets(self) -> None:
        total = volume_of(
            SetEntry(reps_done=10, load_kg=Decimal("60")),
            SetEntry(reps_done=8, load_kg=Decimal("70")),
            SetEntry(reps_done=6, load_kg=Decimal("80")),
        )
        assert total == Decimal("1640")  # 600 + 560 + 480

    def test_empty_input_is_zero_not_none(self) -> None:
        """A session with nothing logged must chart as 0, never crash or render blank."""
        assert volume_of() == Decimal("0")


class TestEdgeCases:
    def test_zero_reps_contributes_nothing(self) -> None:
        """Set opened, load entered, no rep performed."""
        total = volume_of(
            SetEntry(reps_done=10, load_kg=Decimal("50")),
            SetEntry(reps_done=0, load_kg=Decimal("50")),
        )
        assert total == Decimal("500")

    def test_bodyweight_exercise_contributes_zero_volume(self) -> None:
        """Pull-ups, push-ups, dips: load is 0 and Σ(reps × 0) = 0.

        This is mathematically right but product-surprising — 40 hard pull-ups score zero
        volume. Pinned here so the behaviour is a deliberate, documented decision rather
        than something discovered later in production.
        """
        assert volume_of(SetEntry(reps_done=12, load_kg=Decimal("0"))) == Decimal("0")

    def test_null_load_is_treated_as_zero_not_an_error(self) -> None:
        """``load_kg`` is nullable in the schema; an offline client may omit it."""
        assert volume_of(SetEntry(reps_done=12, load_kg=None)) == Decimal("0")

    def test_null_reps_is_treated_as_zero_not_an_error(self) -> None:
        assert volume_of(SetEntry(reps_done=None, load_kg=Decimal("60"))) == Decimal("0")

    def test_uncompleted_set_is_excluded(self) -> None:
        """A set left unticked did not happen; counting it would inflate progression."""
        total = volume_of(
            SetEntry(reps_done=10, load_kg=Decimal("60"), is_completed=True),
            SetEntry(reps_done=10, load_kg=Decimal("60"), is_completed=False),
        )
        assert total == Decimal("600")

    def test_partially_completed_session(self) -> None:
        """Realistic: 3 sets planned, client did 2 then left."""
        total = volume_of(
            SetEntry(reps_done=12, load_kg=Decimal("40"), is_completed=True),
            SetEntry(reps_done=10, load_kg=Decimal("40"), is_completed=True),
            SetEntry(reps_done=0, load_kg=Decimal("40"), is_completed=False),
        )
        assert total == Decimal("880")

    def test_all_sets_uncompleted_is_zero(self) -> None:
        total = volume_of(
            SetEntry(reps_done=10, load_kg=Decimal("60"), is_completed=False),
            SetEntry(reps_done=10, load_kg=Decimal("60"), is_completed=False),
        )
        assert total == Decimal("0")


class TestNumericPrecision:
    def test_fractional_load_is_exact(self) -> None:
        """2.5 kg micro-plates are standard. Float arithmetic would drift here.

        With floats, 3 × (10 × 2.5) style accumulation across a training block produces
        visible rounding on the progress chart. Decimal keeps it exact.
        """
        assert volume_of(SetEntry(reps_done=10, load_kg=Decimal("2.5"))) == Decimal("25.0")

    def test_returns_decimal_not_float(self) -> None:
        result = volume_of(SetEntry(reps_done=10, load_kg=Decimal("60")))
        assert isinstance(result, Decimal), f"expected Decimal, got {type(result).__name__}"

    def test_accumulation_does_not_drift(self) -> None:
        """100 sets of 0.1 kg: exact in Decimal, 0.9999999999999999 in float."""
        sets = [SetEntry(reps_done=1, load_kg=Decimal("0.1")) for _ in range(100)]
        assert volume_of(*sets) == Decimal("10.0")

    def test_heavy_realistic_session_total(self) -> None:
        total = volume_of(
            SetEntry(reps_done=5, load_kg=Decimal("100")),
            SetEntry(reps_done=5, load_kg=Decimal("102.5")),
            SetEntry(reps_done=3, load_kg=Decimal("110")),
        )
        assert total == Decimal("1342.5")


class TestRobustness:
    def test_negative_reps_are_rejected_or_ignored(self) -> None:
        """A corrupted offline payload must not be able to *reduce* recorded volume."""
        try:
            total = volume_of(
                SetEntry(reps_done=10, load_kg=Decimal("60")),
                SetEntry(reps_done=-5, load_kg=Decimal("60")),
            )
        except (ValueError, AssertionError):
            return  # rejecting is acceptable
        assert total >= Decimal("600"), (
            "a negative reps_done reduced the total; a malformed offline replay could "
            "silently erase a client's recorded progression"
        )

    def test_accepts_any_iterable_not_just_a_list(self) -> None:
        compute_volume = require("app.domain.volume", "compute_volume")
        generator = (SetEntry(reps_done=10, load_kg=Decimal("60")) for _ in range(2))
        assert compute_volume(generator) == Decimal("1200")


@pytest.mark.parametrize(
    ("reps", "load", "expected"),
    [
        (0, "0", "0"),
        (0, "100", "0"),
        (1, "0", "0"),
        (1, "1", "1"),
        (12, "2.5", "30.0"),
        (8, "0.5", "4.0"),
        (100, "20", "2000"),
    ],
)
def test_volume_table(reps: int, load: str, expected: str) -> None:
    assert volume_of(SetEntry(reps_done=reps, load_kg=Decimal(load))) == Decimal(expected)
