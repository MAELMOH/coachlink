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


def _run_privileged(owner_url: str, statements: list[str]) -> None:
    """Execute owner-level DDL/GRANTs outside a transaction (roles need AUTOCOMMIT)."""
    import sqlalchemy

    engine = sqlalchemy.create_engine(database.to_psycopg(owner_url), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            for statement in statements:
                conn.execute(sqlalchemy.text(statement))
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def db_endpoint() -> database.DbEndpoint:
    """The test database, with the unprivileged application role guaranteed to exist.

    The role is bootstrapped *here* rather than in ``app_url`` on purpose. The RLS
    migration issues ``CREATE POLICY ... TO coachlink_app``, which fails outright if the
    role is missing, and ``test_app_role_is_not_superuser_and_cannot_bypass_rls`` asks
    ``pg_roles`` about it while holding only an owner connection. Creating it lazily in
    ``app_url`` made both depend on the order fixtures happen to be requested in.
    """
    endpoint = database.resolve_endpoint()
    if endpoint is None:
        pytest.skip(database.skip_reason())

    if not os.environ.get("TEST_DATABASE_URL_APP"):
        _run_privileged(
            endpoint.url,
            [
                database.ENSURE_APP_ROLE_SQL,
                f"GRANT USAGE ON SCHEMA public TO {database.APP_ROLE}",
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                f"TO {database.APP_ROLE}",
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, "
                f"DELETE ON TABLES TO {database.APP_ROLE}",
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES "
                f"TO {database.APP_ROLE}",
            ],
        )
    return endpoint


@pytest.fixture(scope="session")
def owner_url(db_endpoint: database.DbEndpoint) -> str:
    """Privileged URL: owns the schema, runs migrations. NOT used for RLS assertions."""
    return db_endpoint.url


@pytest.fixture(scope="session")
def app_url(db_endpoint: database.DbEndpoint) -> str:
    """Unprivileged URL (``coachlink_app``) — the only one RLS tests may use."""
    provided = os.environ.get("TEST_DATABASE_URL_APP")
    if provided:
        return database.to_asyncpg(provided)
    return database.with_credentials(db_endpoint.url, database.APP_ROLE, database.APP_ROLE_PASSWORD)


@pytest.fixture(scope="session")
def schema_ready(owner_url: str) -> bool:
    """Build the schema once per session by running the **Alembic migrations**.

    Not ``Base.metadata.create_all``: that emits tables and indexes only, leaving the
    database with zero RLS policies, no citext e-mail, no ``updated_at`` trigger and no
    ``resolve_invitation`` function. See ``tests/support/schema.py`` for the full
    rationale. As a bonus, the migration chain is exercised on every run.
    """
    if not is_available("app.models.base", "Base"):
        pytest.skip("app/models not available yet (waiting on `back`)")

    from tests.support import schema

    schema.upgrade_to_head(owner_url)

    # Tables created by the migration are covered by ALTER DEFAULT PRIVILEGES above,
    # but re-granting is idempotent and keeps the suite working against a pre-existing
    # CI database whose defaults were never set.
    _run_privileged(
        owner_url,
        [
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
            f"TO {database.APP_ROLE}",
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {database.APP_ROLE}",
        ],
    )
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
