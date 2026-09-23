"""Rate limiting backends.

Redis-backed in production (the counter must be shared across uvicorn workers);
an in-memory fallback keeps dev and unit tests running without Redis.
"""

from __future__ import annotations

import time
from typing import Protocol

from redis.asyncio import Redis

__all__ = ["InMemoryRateLimiter", "NullRateLimiter", "RateLimiter", "RedisRateLimiter"]


class RateLimiter(Protocol):
    async def check(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        """Return ``(allowed, retry_after_seconds)``."""
        ...


class RedisRateLimiter:
    """Fixed-window counter. One INCR + one EXPIRE, pipelined."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def check(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        window = int(time.time()) // window_seconds
        redis_key = f"rl:{key}:{window}"
        pipe = self._redis.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window_seconds)
        count, _ = await pipe.execute()
        if int(count) > limit:
            retry_after = window_seconds - (int(time.time()) % window_seconds)
            return False, max(retry_after, 1)
        return True, 0


class InMemoryRateLimiter:
    """Per-process fallback. Correct for one worker, good enough for dev/tests."""

    def __init__(self) -> None:
        self._counters: dict[tuple[str, int], int] = {}

    async def check(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        window = int(time.time()) // window_seconds
        # Drop stale windows so the dict cannot grow unbounded.
        self._counters = {k: v for k, v in self._counters.items() if k[1] >= window}
        counter_key = (key, window)
        count = self._counters.get(counter_key, 0) + 1
        self._counters[counter_key] = count
        if count > limit:
            retry_after = window_seconds - (int(time.time()) % window_seconds)
            return False, max(retry_after, 1)
        return True, 0


class NullRateLimiter:
    """Disables limiting entirely — tests that are not about rate limiting."""

    async def check(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        return True, 0
