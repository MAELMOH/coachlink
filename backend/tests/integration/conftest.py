"""Fixtures for API-level tests.

The app is built per test through ``create_app()`` so that ``dependency_overrides`` from
one test can never bleed into another, and driven in-process with
``httpx.ASGITransport`` — no socket, no uvicorn, no port collisions in CI.
"""

from __future__ import annotations

import pytest

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
async def client(api_app):
    httpx = pytest.importorskip("httpx")
    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://coachlink.test") as c:
        yield c


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
