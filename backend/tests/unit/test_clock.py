"""Injectable clock (``app/core/clock.py``).

``FrozenClock`` is not a convenience — it is load-bearing for every dated rule in the
product: the 10-day trial, the read-only switch at expiry, ``is_client_active``,
invitation expiry, presigned-URL TTLs. If it can be fed an ambiguous instant, every
downstream assertion inherits that ambiguity.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.core.clock import FrozenClock, SystemClock

PARIS = timezone(timedelta(hours=2))  # CEST, the product's home offset


class TestSystemClock:
    def test_is_timezone_aware_utc(self) -> None:
        now = SystemClock().now()
        assert now.tzinfo is not None, "a naive datetime would corrupt every dated rule"
        assert now.utcoffset() == timedelta(0)

    def test_both_implementations_satisfy_the_protocol(self) -> None:
        """Structural check.

        ``Clock`` is not ``@runtime_checkable``, so ``isinstance`` raises rather than
        answering. Assert the shape directly instead of asking ``back`` to change the
        Protocol purely for the test's benefit: a clock is anything with a no-argument
        ``now()`` returning an aware UTC datetime.
        """
        for clock in (SystemClock(), FrozenClock(datetime(2026, 9, 22, tzinfo=UTC))):
            assert callable(getattr(clock, "now", None))
            moment = clock.now()
            assert isinstance(moment, datetime)
            assert moment.utcoffset() == timedelta(0)


class TestFrozenClock:
    def test_does_not_move_on_its_own(self) -> None:
        clock = FrozenClock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        first = clock.now()
        second = clock.now()
        assert first == second

    def test_normalises_to_utc(self) -> None:
        clock = FrozenClock(datetime(2026, 9, 22, 14, 0, tzinfo=PARIS))
        assert clock.now() == datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
        assert clock.now().utcoffset() == timedelta(0)

    def test_advance_moves_forward(self) -> None:
        clock = FrozenClock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        clock.advance(timedelta(days=10))
        assert clock.now() == datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    def test_advance_accepts_negative_delta(self) -> None:
        clock = FrozenClock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        clock.advance(timedelta(hours=-3))
        assert clock.now() == datetime(2026, 9, 22, 9, 0, tzinfo=UTC)

    def test_set_replaces_the_instant(self) -> None:
        clock = FrozenClock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        clock.set(datetime(2027, 1, 1, 0, 0, tzinfo=UTC))
        assert clock.now() == datetime(2027, 1, 1, 0, 0, tzinfo=UTC)

    def test_set_normalises_a_non_utc_instant(self) -> None:
        clock = FrozenClock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        clock.set(datetime(2026, 9, 22, 14, 0, tzinfo=PARIS))
        assert clock.now() == datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


class TestNaiveDatetimeRejection:
    """A naive datetime must never enter the clock — through *any* door.

    ``__init__`` guards against it. ``set()`` currently does not: it calls
    ``astimezone(UTC)``, which on a naive input silently assumes the *machine's local
    timezone*. On a CI runner in UTC that is invisible; on the developer machine (Europe
    /Paris, UTC+2) the same test would see the instant shift by two hours. A trial that
    expires "in 10 days" would then flip a day early or late depending on who ran the
    suite — the classic test that is green locally and red in CI, or worse, green in both
    while the rule is wrong.
    """

    def test_constructor_rejects_naive(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            FrozenClock(datetime(2026, 9, 22, 12, 0))

    def test_set_rejects_naive(self) -> None:
        clock = FrozenClock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        with pytest.raises(ValueError, match="timezone-aware"):
            clock.set(datetime(2026, 9, 22, 12, 0))

    def test_set_does_not_silently_reinterpret_a_naive_instant(self) -> None:
        """Belt-and-braces: even if `set` accepted naive input, it must not shift it.

        Stated as a separate assertion so the failure report distinguishes "no validation"
        from "validation absent *and* the value was mangled".
        """
        clock = FrozenClock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        try:
            clock.set(datetime(2026, 9, 22, 12, 0))
        except ValueError:
            return  # rejected outright: the desired behaviour
        assert clock.now() == datetime(2026, 9, 22, 12, 0, tzinfo=UTC), (
            "set() accepted a naive datetime and reinterpreted it in the machine's local "
            "timezone; dated business rules become machine-dependent"
        )
