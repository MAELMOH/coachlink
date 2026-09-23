"""UUID v7 generation (RFC 9562).

PostgreSQL 16 has no native ``uuidv7()`` (it lands in PG18), so we generate the
identifier application-side. Pure function, no I/O: keep it that way.

Layout (128 bits)::

    | 48 bits unix_ts_ms | 4 bits ver=7 | 12 bits rand_a | 2 bits var | 62 bits rand_b |

``rand_a`` is used as a monotonic sub-millisecond counter so that two ids created
inside the same millisecond still sort in creation order. That monotonicity is
what makes our cursor-based pagination (ARCHITECTURE.md §8) correct.
"""

from __future__ import annotations

import os
import threading
import time
from uuid import UUID

__all__ = ["uuid7", "uuid7_timestamp_ms"]

_MAX_COUNTER = 0xFFF  # 12 bits of rand_a used as the intra-millisecond counter

_lock = threading.Lock()
_last_ms: int = -1
_counter: int = 0


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def uuid7(*, _ms: int | None = None) -> UUID:
    """Return a time-ordered UUID v7.

    ``_ms`` is an injection point for tests only; production callers pass nothing.
    """
    global _last_ms, _counter

    with _lock:
        ms = _now_ms() if _ms is None else _ms
        if ms > _last_ms:
            _last_ms = ms
            # Seed the counter low so a burst inside one millisecond cannot overflow.
            _counter = int.from_bytes(os.urandom(2), "big") & 0x0FF
        else:
            # Clock went backwards or same millisecond: keep growing monotonically.
            ms = _last_ms
            _counter += 1
            if _counter > _MAX_COUNTER:
                # Counter exhausted: borrow the next millisecond rather than repeat.
                _last_ms += 1
                ms = _last_ms
                _counter = 0
        counter = _counter

    value = (ms & 0xFFFF_FFFF_FFFF) << 80
    value |= 0x7 << 76
    value |= (counter & _MAX_COUNTER) << 64
    value |= 0b10 << 62
    value |= int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
    return UUID(int=value)


def uuid7_timestamp_ms(value: UUID) -> int:
    """Extract the embedded unix-epoch milliseconds from a UUID v7."""
    if value.version != 7:
        raise ValueError(f"not a UUID v7: version={value.version}")
    return value.int >> 80
