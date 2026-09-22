"""Injectable clock.

Every dated business rule in CoachLink — the 10-day trial, the read-only switch at
expiry, ``is_client_active(link, month)``, invitation expiry, presigned-URL TTLs —
must be testable without cheating on the database. So nothing outside this module
calls ``datetime.now()`` directly:

* services depend on :func:`app.core.deps.get_clock`;
* pure functions in ``app/domain`` take ``now`` as an explicit argument.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

__all__ = ["Clock", "SystemClock", "FrozenClock"]


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Current instant, always timezone-aware in UTC."""
        ...


class SystemClock:
    """Production clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)


def _as_utc(at: datetime) -> datetime:
    """Normalise to UTC, refusing naive input.

    ``datetime.astimezone()`` on a naive value silently assumes the *machine's local
    timezone*. That would make every dated rule machine-dependent: on a UTC+2 developer
    machine ``set(datetime(2026, 9, 22, 12, 0))`` lands on 10:00 UTC, on a UTC CI runner
    on 12:00 UTC, and a "trial expires in 10 days" assertion flips a day depending on who
    ran the suite. Refuse the ambiguity instead of resolving it arbitrarily.
    """
    if at.tzinfo is None:
        raise ValueError("FrozenClock requires a timezone-aware datetime")
    return at.astimezone(UTC)


class FrozenClock:
    """Test clock. Lives in app/ (not tests/) so QA and workers share one implementation."""

    def __init__(self, at: datetime) -> None:
        self._at = _as_utc(at)

    def now(self) -> datetime:
        return self._at

    def set(self, at: datetime) -> None:
        self._at = _as_utc(at)

    def advance(self, delta: timedelta) -> None:
        self._at += delta
