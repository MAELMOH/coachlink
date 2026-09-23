"""Provisioning of a REAL PostgreSQL 16 for the test suite.

Why not SQLite: CoachLink's number-one risk is a coach reading another coach's client
data, and the second barrier against it is a PostgreSQL **Row Level Security** policy.
RLS does not exist in SQLite. A green test suite on SQLite would prove nothing about the
barrier that actually matters, so integration and RLS tests run on Postgres or they are
skipped — never silently downgraded.

Three modes, tried in order:

1. ``TEST_DATABASE_URL`` is set  -> use it as-is (CI service container).
2. Docker daemon answers        -> testcontainers starts a throwaway Postgres 16.
3. Neither                      -> tests marked ``integration`` / ``rls`` are SKIPPED
   with an explicit reason, so ``pytest -m "not integration and not rls"`` stays usable
   on a laptop with no Docker running.

Two roles, on purpose
---------------------
* ``coachlink_owner`` — owns the tables, runs Alembic. May be the bootstrap superuser.
* ``coachlink_app``   — ``NOSUPERUSER NOBYPASSRLS``, what the API actually connects as.

A superuser silently bypasses every RLS policy. Running the isolation tests as one would
make them pass while testing nothing at all, which is strictly worse than not having
them. Hence :func:`ensure_app_role` and the ``test_app_role_cannot_bypass_rls`` guard in
``tests/rls/``.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

__all__ = [
    "APP_ROLE",
    "APP_ROLE_PASSWORD",
    "DbEndpoint",
    "docker_available",
    "resolve_endpoint",
    "to_asyncpg",
    "to_psycopg",
    "with_credentials",
]

APP_ROLE = "coachlink_app"
APP_ROLE_PASSWORD = "coachlink_app_test_pwd"  # test-only, never a production secret


@dataclass(frozen=True)
class DbEndpoint:
    """Where the test database lives, plus how we got there (for skip messages)."""

    url: str
    origin: str  # "env" | "testcontainers"


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _swap_driver(url: str, driver: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme.split("+", 1)[0]
    return urlunsplit((f"{scheme}+{driver}", parts.netloc, parts.path, parts.query, parts.fragment))


def to_asyncpg(url: str) -> str:
    """Normalise any postgres URL to the SQLAlchemy asyncpg driver."""
    return _swap_driver(url, "asyncpg")


def to_psycopg(url: str) -> str:
    """Normalise to the sync psycopg driver (used for schema bootstrap only)."""
    return _swap_driver(url, "psycopg")


def with_credentials(url: str, user: str, password: str) -> str:
    """Return ``url`` rewritten to authenticate as ``user`` — how we drop to the app role."""
    parts = urlsplit(url)
    host = parts.hostname or "localhost"
    netloc = f"{user}:{password}@{host}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def docker_available() -> bool:
    """True when a Docker daemon actually answers.

    ``docker`` being on PATH is not enough — Docker Desktop is frequently installed but
    not running, which is exactly the situation on the current dev machine.
    """
    if os.environ.get("COACHLINK_NO_DOCKER"):
        return False
    try:
        completed = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


_container = None  # kept alive for the whole session; stopped by the session fixture


@lru_cache(maxsize=1)
def resolve_endpoint() -> DbEndpoint | None:
    """Return the test database endpoint, or ``None`` if none can be provided."""
    global _container

    env_url = os.environ.get("TEST_DATABASE_URL")
    if env_url:
        return DbEndpoint(url=to_asyncpg(env_url), origin="env")

    if not docker_available():
        return None

    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        return None

    try:
        _container = PostgresContainer("postgres:16-alpine")
        _container.start()
    except Exception:
        _container = None
        return None

    return DbEndpoint(url=to_asyncpg(_container.get_connection_url()), origin="testcontainers")


def shutdown() -> None:
    """Stop a testcontainers instance if we started one."""
    global _container
    if _container is not None:
        try:
            _container.stop()
        finally:
            _container = None


def skip_reason() -> str:
    return (
        "no PostgreSQL available: set TEST_DATABASE_URL (CI service container) or start "
        "the Docker daemon so testcontainers can provide one. These tests are NOT run "
        "against SQLite on purpose — RLS policies do not exist there "
        "(see tests/support/database.py)."
    )


# ---------------------------------------------------------------------------
# Role bootstrap
# ---------------------------------------------------------------------------

ENSURE_APP_ROLE_SQL = f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
        CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_ROLE_PASSWORD}'
            NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB;
    ELSE
        ALTER ROLE {APP_ROLE} WITH LOGIN PASSWORD '{APP_ROLE_PASSWORD}'
            NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB;
    END IF;
END
$$;
"""
