"""Root pytest configuration for the CoachLink backend suite.

Layout::

    tests/unit/         pure domain logic, no I/O, runs everywhere, always fast
    tests/integration/  HTTP API through httpx.AsyncClient against a REAL Postgres
    tests/rls/          Row Level Security policies, exercised in raw SQL as the
                        unprivileged app role (the second barrier, tested on its own)
    tests/rgpd/         encryption, consent, purge, log/push PII leakage
    tests/support/      helpers, not collected as tests

Design rules for this suite
---------------------------
* **Never fall back to SQLite.** See ``tests/support/database.py``.
* **Never run privileged.** RLS tests connect as ``coachlink_app``
  (``NOSUPERUSER NOBYPASSRLS``); a superuser would bypass every policy and turn the
  isolation suite into theatre.
* **Assert on error codes, never on messages.** ``message`` is human-facing and
  translatable; ``code`` is the frozen contract (``app/core/errors.py``).
* **Time is injected, never real.** Anything dated uses ``FrozenClock``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from tests.support import database
from tests.support.pending import is_available

# A fixed, unambiguous instant for every dated assertion in the suite.
# Chosen mid-month and mid-day so that "+10 days" never crosses a month or DST boundary
# by accident, which would make trial-expiry tests flaky for the wrong reason.
REFERENCE_NOW = datetime(2026, 9, 22, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Marker plumbing
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Register QA-owned markers here rather than in ``pyproject.toml``.

    ``pyproject.toml`` belongs to ``back`` and both of us editing it invites conflicts.
    ``--strict-markers`` is satisfied by registration from any plugin, so the QA-specific
    markers live with the QA suite. ``integration`` and ``rls`` stay in ``pyproject.toml``
    because ``devops`` filters CI jobs on them.
    """
    config.addinivalue_line(
        "markers", "rgpd: verifies a GDPR guarantee (encryption, consent, erasure, PII)"
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip DB-backed tests with an explicit reason when no PostgreSQL is reachable.

    This keeps ``pytest`` runnable on a laptop without Docker while making it obvious in
    the report that the isolation guarantees were *not* verified in that run.
    """
    needs_db = {"integration", "rls"}
    if not any(needs_db & {m.name for m in item.iter_markers()} for item in items):
        return

    if database.resolve_endpoint() is not None:
        return

    skip = pytest.mark.skip(reason=database.skip_reason())
    for item in items:
        if needs_db & {m.name for m in item.iter_markers()}:
            item.add_marker(skip)


def pytest_report_header(config: pytest.Config) -> list[str]:
    endpoint = database.resolve_endpoint()
    if endpoint is None:
        return ["coachlink: NO PostgreSQL -> integration/rls tests SKIPPED (not SQLite-faked)"]
    return [f"coachlink: PostgreSQL via {endpoint.origin}"]


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    database.shutdown()


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------


@pytest.fixture
def reference_now() -> datetime:
    """The single instant the whole suite pivots around."""
    return REFERENCE_NOW


@pytest.fixture
def frozen_clock():
    """``FrozenClock`` positioned at :data:`REFERENCE_NOW`.

    Uses ``back``'s implementation from ``app/core/clock.py`` rather than a QA-local
    double, so the workers, the services and the tests all share one notion of "now".
    """
    frozen_clock_cls = pytest.importorskip(
        "app.core.clock", reason="app/core/clock.py not available yet"
    ).FrozenClock
    return frozen_clock_cls(REFERENCE_NOW)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def db_endpoint() -> database.DbEndpoint:
    endpoint = database.resolve_endpoint()
    if endpoint is None:
        pytest.skip(database.skip_reason())
    return endpoint


@pytest.fixture(scope="session")
def owner_url(db_endpoint: database.DbEndpoint) -> str:
    """Privileged URL: owns the schema, runs migrations. NOT used for RLS assertions."""
    return db_endpoint.url


@pytest.fixture(scope="session")
def app_url(db_endpoint: database.DbEndpoint) -> str:
    """Unprivileged URL (``coachlink_app``) — the only one RLS tests may use.

    The role is created on the fly when the environment did not provide it, so the suite
    works both against a CI service container and a throwaway testcontainer.
    """
    sqlalchemy = pytest.importorskip("sqlalchemy")

    provided = os.environ.get("TEST_DATABASE_URL_APP")
    if provided:
        return database.to_asyncpg(provided)

    engine = sqlalchemy.create_engine(
        database.to_psycopg(db_endpoint.url), isolation_level="AUTOCOMMIT"
    )
    try:
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text(database.ENSURE_APP_ROLE_SQL))
            db_name = conn.execute(sqlalchemy.text("SELECT current_database()")).scalar_one()
            conn.execute(
                sqlalchemy.text(f'GRANT CONNECT ON DATABASE "{db_name}" TO {database.APP_ROLE}')
            )
            conn.execute(sqlalchemy.text(f"GRANT USAGE ON SCHEMA public TO {database.APP_ROLE}"))
            conn.execute(
                sqlalchemy.text(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                    f"TO {database.APP_ROLE}"
                )
            )
            conn.execute(
                sqlalchemy.text(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, "
                    f"DELETE ON TABLES TO {database.APP_ROLE}"
                )
            )
    finally:
        engine.dispose()

    return database.with_credentials(db_endpoint.url, database.APP_ROLE, database.APP_ROLE_PASSWORD)


@pytest.fixture(scope="session")
def schema_ready(owner_url: str) -> bool:
    """Create the schema from ``Base.metadata`` once per session.

    Skips cleanly while ``back`` has not landed ``app/models`` yet, so the DB fixtures
    can already be wired and exercised by the RLS role checks.
    """
    if not is_available("app.models.base", "Base"):
        pytest.skip("app/models not available yet (waiting on `back`)")

    sqlalchemy = pytest.importorskip("sqlalchemy")
    from app.models.base import Base

    engine = sqlalchemy.create_engine(database.to_psycopg(owner_url))
    try:
        with engine.begin() as conn:
            Base.metadata.create_all(conn)
    finally:
        engine.dispose()
    return True


@pytest.fixture
async def owner_engine(owner_url: str) -> Iterator[object]:
    """Async engine with schema-owner privileges (fixture setup / teardown only)."""
    sa_async = pytest.importorskip("sqlalchemy.ext.asyncio")
    engine = sa_async.create_async_engine(owner_url, poolclass=None)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def app_engine(app_url: str) -> Iterator[object]:
    """Async engine bound to the UNPRIVILEGED role. Use this for anything RLS-related."""
    sa_async = pytest.importorskip("sqlalchemy.ext.asyncio")
    engine = sa_async.create_async_engine(app_url, poolclass=None)
    try:
        yield engine
    finally:
        await engine.dispose()
