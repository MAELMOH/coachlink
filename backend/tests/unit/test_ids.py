"""UUID v7 (``app/domain/ids.py``).

Why this matters beyond "ids are unique": cursor-based pagination (ARCHITECTURE.md §8)
orders rows by primary key. If two ids minted in the same millisecond can compare out of
creation order, a paginated feed can silently drop or repeat a row at the page boundary.
Monotonicity is therefore a correctness requirement, not a nicety.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from uuid import UUID

import pytest

from app.domain import ids as ids_module
from app.domain.ids import uuid7, uuid7_timestamp_ms


@pytest.fixture(autouse=True)
def _isolate_generator_state() -> Iterator[None]:
    """Restore ``uuid7``'s module-global monotonic state after every test.

    ``uuid7`` deliberately keeps ``_last_ms``/``_counter`` at module level so that ids
    stay ordered across calls. The consequence for tests is that injecting a far-future
    ``_ms`` (as the backwards-clock test does) would leave the generator pinned in the
    future for the remainder of the session and break unrelated assertions. Snapshot and
    restore rather than let test order matter.
    """
    saved = (ids_module._last_ms, ids_module._counter)
    yield
    ids_module._last_ms, ids_module._counter = saved


class TestLayout:
    def test_version_is_7(self) -> None:
        assert uuid7().version == 7

    def test_variant_is_rfc4122(self) -> None:
        # Bits 64-65 must be 0b10. `UUID.variant` spells that out for us.
        from uuid import RFC_4122

        assert uuid7().variant == RFC_4122

    def test_timestamp_matches_wall_clock(self) -> None:
        before = time.time_ns() // 1_000_000
        value = uuid7()
        after = time.time_ns() // 1_000_000

        embedded = uuid7_timestamp_ms(value)
        # Inclusive bounds: the generator may borrow a millisecond under contention.
        assert before <= embedded <= after + 1

    def test_timestamp_extraction_rejects_other_versions(self) -> None:
        uuid4_value = UUID("d9428888-122b-11e1-b85c-61cd3cbb3210")  # a v1
        with pytest.raises(ValueError, match="not a UUID v7"):
            uuid7_timestamp_ms(uuid4_value)

    def test_round_trip_through_string(self) -> None:
        value = uuid7()
        assert uuid7_timestamp_ms(UUID(str(value))) == uuid7_timestamp_ms(value)


class TestMonotonicity:
    def test_sequential_ids_strictly_increase(self) -> None:
        values = [uuid7() for _ in range(2_000)]
        assert values == sorted(values), "uuid7 must be sortable in creation order"
        assert len(set(values)) == len(values), "uuid7 must not collide"

    def test_monotonic_within_a_single_millisecond(self) -> None:
        """The hard case: the intra-millisecond counter carries the ordering.

        ``_ms`` is the module's documented test injection point, so we can pin every id
        to the same millisecond instead of hoping the loop is fast enough.
        """
        pinned = time.time_ns() // 1_000_000
        values = [uuid7(_ms=pinned) for _ in range(500)]

        assert values == sorted(values)
        assert len(set(values)) == len(values)

    def test_clock_going_backwards_does_not_break_ordering(self) -> None:
        """A backwards system clock (NTP correction, VM resume) must not reorder ids."""
        now_ms = time.time_ns() // 1_000_000
        forward = uuid7(_ms=now_ms + 5_000)
        backward = uuid7(_ms=now_ms - 5_000)

        assert backward > forward, (
            "an id minted after a backwards clock jump must still sort last, "
            "otherwise cursor pagination can skip rows"
        )

    def test_concurrent_generation_is_unique_and_ordered(self) -> None:
        """The generator is shared module state guarded by a lock; prove the lock works."""
        produced: list[UUID] = []
        lock = threading.Lock()

        def worker() -> None:
            local = [uuid7() for _ in range(200)]
            with lock:
                produced.extend(local)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(produced) == 1_600
        assert len(set(produced)) == 1_600, "concurrent uuid7() produced a collision"
