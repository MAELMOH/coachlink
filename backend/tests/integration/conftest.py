"""Fixtures for API-level tests.

The app is built per test through ``create_app()`` so that ``dependency_overrides`` from
one test can never bleed into another, and driven in-process with
``httpx.ASGITransport`` — no socket, no uvicorn, no port collisions in CI.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import Request

from tests.support.pending import is_available, require


@pytest.fixture
def api_app():
    """A fresh FastAPI instance.

    ``back`` exposes ``create_app()`` precisely so tests get an isolated app rather than
    the module-level singleton uvicorn serves.
    """
    create_app = require("app.main", "create_app")
    return create_app()


@pytest.fixture
async def client(api_app, app_url, schema_ready) -> AsyncIterator:
    """HTTP client whose requests hit the **test** database, as the app role.

    Every API test goes through this, including the ones that never look at a row.
    Three reasons it overrides ``get_session`` rather than letting the real dependency
    run:

    * **Correctness.** ``app.core.db`` caches its engine in a module-level global. Under
      ``pytest-asyncio`` each test gets a fresh event loop, so the second test to touch
      that global inherits an asyncpg pool bound to a *closed* loop and fails with
      "Event loop is closed" — intermittently, and in whichever test happens to run
      second. Binding a per-test engine removes the whole class of flake.
    * **Isolation.** The real dependency connects to ``COACHLINK_DATABASE_URL``, i.e.
      the developer's own dev database. A suite that quietly writes there is a suite
      nobody trusts.
    * **Realism.** It connects as ``coachlink_app`` (NOSUPERUSER, NOBYPASSRLS), so every
      request passes through the RLS policies exactly as production does. Running as the
      owner would make cross-tenant assertions pass for the wrong reason.

    The RLS context is derived from the request's own bearer token, mirroring
    ``app.core.deps.get_session`` — the point is to exercise that behaviour, not to hand
    the session a pre-set identity the real app would not have.
    """
    httpx = pytest.importorskip("httpx")
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.db import apply_rls_context
    from app.core.deps import get_session
    from app.core.errors import ApiError
    from app.core.security import decode_token

    engine = create_async_engine(app_url, poolclass=None)
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    # The annotation is load-bearing, and `Request` must be imported at module level:
    # FastAPI resolves an un-annotated (or unresolvable, under `from __future__ import
    # annotations`) parameter as a *query* parameter, which silently turns every
    # endpoint into one demanding `?request=` and answers 422 to everything.
    async def _session_override(request: Request):
        user_id = None
        role = None
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() == "bearer" and token:
            try:
                payload = decode_token(token.strip())
                user_id, role = payload.user_id, payload.role
            except ApiError:
                user_id, role = None, None

        request.state.user_id = user_id
        async with maker() as session:
            try:
                await apply_rls_context(session, user_id, role)
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    api_app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://coachlink.test") as c:
        yield c
    api_app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def db_client(client) -> AsyncIterator:
    """Explicit alias of :func:`client`, for tests whose point *is* the database.

    Kept so a reader of ``test_auth_flow.py`` sees at the call site that the test talks
    to a real PostgreSQL rather than a mocked session.
    """
    yield client


@pytest.fixture
def deps_module():
    """``app.core.deps`` — the injection points the API is overridden through."""
    for candidate in ("app.core.deps", "app.api.deps", "app.core.dependencies"):
        if is_available(candidate):
            import importlib

            return importlib.import_module(candidate)
    pytest.xfail("dependency module not available yet (expected app/core/deps.py)")


def error_code(response) -> str | None:
    """Extract ``error.code`` from the normalised envelope (ARCHITECTURE.md §8).

    Tests assert on this, never on ``message``: the message is human-facing and
    translatable, the code is the contract the Flutter app branches on.
    """
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        return code if isinstance(code, str) else None
    return None
