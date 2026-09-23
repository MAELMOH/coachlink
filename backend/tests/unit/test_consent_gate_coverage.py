"""Every route is either exempt or gated — checked without a database.

``tests/integration/test_consent_gate.py`` proves the gate *behaves* (it really answers
403). This file proves it is *wired* everywhere, which is a different failure mode and a
much likelier one: a new router added without the dependency.

It runs in the fast, DB-free part of the suite on purpose. A developer adding an
endpoint should find out in seconds, not after the Postgres service container boots.
"""

from __future__ import annotations

import pytest

from app.api.consent_gate import (
    CONSENT_EXEMPT_EXACT,
    ConsentGateError,
    assert_consent_gate_complete,
    is_exempt,
    iter_effective_routes,
    require_consent,
)
from app.main import create_app


@pytest.fixture(scope="module")
def app():
    return create_app()


def test_the_route_list_is_not_empty(app) -> None:
    """Guard against a vacuous check.

    FastAPI ≥ 0.13x flattens included routers lazily, so a naive walk of ``app.routes``
    returns placeholders and sees no endpoints at all — and then every assertion below
    would pass for having inspected nothing.
    """
    routes = iter_effective_routes(app)
    assert len(routes) > 5, f"only {len(routes)} routes resolved — the walk is not flattening"


def test_every_route_is_exempt_or_gated(app) -> None:
    """The same invariant ``create_app()`` enforces at startup, asserted explicitly."""
    ungated = [
        f"{sorted(methods - {'HEAD', 'OPTIONS'})} {path}"
        for path, methods, deps in iter_effective_routes(app)
        if not is_exempt(path)
        and not any(getattr(dep, "call", None) is require_consent for dep in deps)
    ]
    assert not ungated, "routes with no consent gate: " + ", ".join(ungated)


def test_creating_the_app_refuses_an_ungated_route(app) -> None:
    """The startup check must actually fail — otherwise it is decoration.

    Without this, a bug in `assert_consent_gate_complete` (a wrong attribute name, a
    silently empty dependency list) would make it pass for every app forever, including
    one with a wide-open endpoint.
    """
    from fastapi import APIRouter

    rogue = APIRouter()

    @rogue.get("/api/v1/rogue")
    async def _rogue() -> dict[str, str]:  # pragma: no cover - never called
        return {}

    app.include_router(rogue)
    try:
        with pytest.raises(ConsentGateError, match="rogue"):
            assert_consent_gate_complete(app)
    finally:
        app.routes[:] = [r for r in app.routes if r is not app.routes[-1]]


def test_the_gdpr_self_service_routes_are_exempt() -> None:
    """Over-blocking is as much a GDPR failure as under-blocking: a user who has not
    consented must still be able to consent, export and erase (Art. 15/17/20)."""
    for path in ("/api/v1/me", "/api/v1/me/consents"):
        assert path in CONSENT_EXEMPT_EXACT
        assert is_exempt(path)


def test_auth_routes_are_exempt() -> None:
    """You cannot log in if logging in requires consent."""
    for path in ("/api/v1/auth/register", "/api/v1/auth/login", "/api/v1/auth/refresh"):
        assert is_exempt(path)


def test_business_routes_are_not_accidentally_exempt() -> None:
    """The exemption list is a whitelist; it must not swallow the gated routes."""
    for path in ("/api/v1/coach/clients", "/api/v1/coach/invitations", "/api/v1/links/{link_id}"):
        assert not is_exempt(path)
