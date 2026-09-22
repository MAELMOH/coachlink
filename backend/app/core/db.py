"""Async SQLAlchemy engine + the single place where the RLS context is set.

**The security-critical bit.** The application connects as ``coachlink_app``
(NOSUPERUSER, NOBYPASSRLS), and every PostgreSQL Row Level Security policy reads
``current_setting('app.current_user_id', true)``. That setting is applied here, by
:func:`session_scope`, once per transaction — never by a service, never by a
router. A service that forgot the ``SET LOCAL`` would silently punch through the
second barrier, so services are not given the opportunity.

Fail-closed: when the setting is absent, ``current_setting(..., true)`` returns
NULL and the policies match no row at all.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql import text

from app.core.config import Settings, get_settings

__all__ = [
    "get_engine",
    "get_sessionmaker",
    "session_scope",
    "apply_rls_context",
    "reset_rls_context",
    "dispose_engine",
    "RLS_USER_SETTING",
    "RLS_ROLE_SETTING",
]

#: Names of the PostgreSQL run-time parameters read by the RLS policies.
#: Changing either of these means rewriting every policy — treat as frozen.
RLS_USER_SETTING = "app.current_user_id"
RLS_ROLE_SETTING = "app.current_role"

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    global _engine
    if _engine is None:
        cfg = settings or get_settings()
        _engine = create_async_engine(
            cfg.database_url,
            echo=cfg.db_echo,
            pool_size=cfg.db_pool_size,
            max_overflow=cfg.db_max_overflow,
            pool_pre_ping=True,
            # Server-side statement caching interacts badly with pgbouncer in
            # transaction mode; keep it small and predictable.
            connect_args={"statement_cache_size": 0},
        )
    return _engine


def get_sessionmaker(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(settings),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def apply_rls_context(
    session: AsyncSession, user_id: UUID | None, role: str | None = None
) -> None:
    """Bind the current principal to the transaction, for the RLS policies.

    ``SET LOCAL`` is transaction-scoped, so the value cannot leak to the next
    request that borrows the same pooled connection.

    The values are bound as parameters of ``set_config`` rather than interpolated
    into a ``SET LOCAL`` string: ``SET`` does not accept bind parameters, and
    building that SQL by hand would be an injection vector on a security control.
    """
    await session.execute(
        text("SELECT set_config(:k, :v, true)"),
        {"k": RLS_USER_SETTING, "v": str(user_id) if user_id else ""},
    )
    await session.execute(
        text("SELECT set_config(:k, :v, true)"),
        {"k": RLS_ROLE_SETTING, "v": role or ""},
    )


async def reset_rls_context(session: AsyncSession) -> None:
    """Explicitly clear the principal (used by tests and by anonymous requests)."""
    await apply_rls_context(session, None, None)


@asynccontextmanager
async def session_scope(
    user_id: UUID | None = None,
    role: str | None = None,
    settings: Settings | None = None,
) -> AsyncIterator[AsyncSession]:
    """Transactional session with the RLS context already applied.

    Used by Celery workers and scripts. HTTP requests go through
    ``app.core.deps.get_session``, which wraps this same helper.
    """
    maker = get_sessionmaker(settings)
    async with maker() as session:
        try:
            await apply_rls_context(session, user_id, role)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
