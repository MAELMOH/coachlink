"""The blocking consent gate (ARCHITECTURE.md §5.2).

    "Bloquant : à l'onboarding, tant que ``tos``, ``privacy`` et ``health_data`` ne sont
    pas accordés, l'API renvoie ``403 CONSENT_REQUIRED`` sur toute route métier."

**"Toute route métier"** is why this module sweeps the router instead of sampling a few
endpoints. A consent gate that covers 90% of routes is not a consent gate: the one route
that slips through is processing health data without a legal basis, and it will be the one
added last, by whoever forgot the decorator.

The sweep is built from the app's own route table, so a route added tomorrow is covered
today. ``back`` implements the gate as a **whitelist** (deny by default) — this suite is
the check that the whitelist has not quietly grown.
"""

from __future__ import annotations

import re
import uuid

import pytest

from tests.integration.conftest import error_code
from tests.support.pending import require

pytestmark = pytest.mark.integration

#: Routes legitimately reachable without the mandatory consents, per `back`.
#: Anything outside this set must answer 403 CONSENT_REQUIRED.
#:
#: The RGPD-critical part is that `/me/consents`, `/me/data-export` and
#: `/me/delete-account` stay open: a user must be able to read, export and erase their
#: data — and to grant the missing consent — without first granting it. A gate that
#: blocked those would make the consent non-revocable in practice.
EXEMPT_EXACT = frozenset(
    {
        "/health",
        # Liveness AND readiness. An orchestrator probe is not a business route, and a
        # readiness check that needed a user's consent could never succeed.
        "/health/ready",
        "/healthz",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/docs/oauth2-redirect",
        "/api/v1/me",
        "/api/v1/me/consents",
        "/api/v1/me/data-export",
        "/api/v1/me/delete-account",
    }
)

EXEMPT_PREFIXES = ("/api/v1/auth/", "/webhooks/")

_PATH_PARAM = re.compile(r"\{[^}]+\}")


def _is_exempt(path: str) -> bool:
    return path in EXEMPT_EXACT or path.startswith(EXEMPT_PREFIXES)


def _concretise(path: str) -> str:
    """Replace ``{id}`` placeholders with a syntactically valid UUID.

    The resource will not exist, which is fine and in fact useful: the consent gate must
    fire *before* the handler looks anything up. A 404 here would mean the gate runs too
    late and the endpoint already touched the database.
    """
    return _PATH_PARAM.sub(str(uuid.uuid4()), path)


def _business_routes(app) -> list[tuple[str, str]]:
    """Every non-exempt endpoint, resolved through the app's own route flattening.

    Iterating ``app.routes`` directly — which this helper originally did — is wrong on
    FastAPI ≥ 0.13x: ``include_router`` stores a lazy ``_IncludedRouter`` placeholder
    instead of copying the child routes in, so the loop sees placeholders with no
    ``path`` and **every mounted endpoint is invisible**. The sweep then finds nothing
    and passes for having checked nothing, which is exactly the failure mode the
    ``test_there_are_business_routes_to_check`` guard below exists to catch.

    ``app.api.consent_gate.iter_effective_routes`` wraps the same helper FastAPI uses to
    build its OpenAPI document, so this suite and the startup check see one route list.
    """
    iter_effective_routes = require("app.api.consent_gate", "iter_effective_routes")

    routes: list[tuple[str, str]] = []
    for path, methods, _dependencies in iter_effective_routes(app):
        if _is_exempt(path):
            continue
        for method in sorted(methods - {"HEAD", "OPTIONS"}):
            routes.append((method, path))
    return sorted(set(routes))


@pytest.fixture
def consentless_client(api_app, deps_module, client):
    """Authenticated user who has granted none of the mandatory consents."""
    get_current_user = getattr(deps_module, "get_current_user", None)
    if get_current_user is None:
        pytest.xfail("app.core.deps.get_current_user not available yet")

    user_factory = require("tests.support.factories", "consentless_user")
    api_app.dependency_overrides[get_current_user] = lambda: user_factory()
    yield client
    api_app.dependency_overrides.clear()


class TestSweep:
    def test_there_are_business_routes_to_check(self, api_app) -> None:
        """Guard against a vacuous sweep.

        Without this, an empty router would make every parametrised test below vanish and
        the suite would report success for having verified nothing.
        """
        routes = _business_routes(api_app)
        assert routes, "no business routes found — the consent sweep would test nothing"

    async def test_every_business_route_is_gated(self, api_app, consentless_client) -> None:
        """One test, all routes, one verdict listing every hole.

        Parametrising per route would be prettier in the report, but the route list has to
        be known at collection time — before the app exists. Sweeping inside the test keeps
        it dynamic, and collecting all failures gives `back` the complete list in one go
        rather than one route per run.
        """
        leaks: list[str] = []
        for method, path in _business_routes(api_app):
            response = await consentless_client.request(method, _concretise(path))
            code = error_code(response)
            if response.status_code != 403 or code != "CONSENT_REQUIRED":
                leaks.append(f"{method} {path} -> {response.status_code} {code}")

        assert not leaks, (
            "routes reachable without the mandatory consents (tos/privacy/health_data):\n"
            + "\n".join(f"  {leak}" for leak in leaks)
            + "\n\nEach one processes personal — often health — data with no legal basis. "
            "The gate is a whitelist: these routes are missing from it, or the guard is "
            "not applied globally."
        )

    async def test_gate_fires_before_the_handler_touches_data(
        self, api_app, consentless_client
    ) -> None:
        """A gated route must never answer 404/422 to a consent-less caller.

        404 would mean the handler already ran a lookup; 422 would mean the body was
        parsed and validated first. Both leak existence information and both mean the
        guard sits too deep in the stack.
        """
        premature: list[str] = []
        for method, path in _business_routes(api_app):
            response = await consentless_client.request(method, _concretise(path))
            if response.status_code in (404, 422):
                premature.append(f"{method} {path} -> {response.status_code}")

        assert not premature, "consent gate runs after the handler on:\n" + "\n".join(premature)


class TestExemptRoutesStayReachable:
    """The mirror image: over-blocking breaks the ability to consent at all."""

    @pytest.mark.parametrize(
        "path",
        ["/api/v1/me", "/api/v1/me/consents"],
    )
    async def test_consent_management_is_reachable_without_consent(
        self, api_app, consentless_client, path: str
    ) -> None:
        response = await consentless_client.get(path)
        if response.status_code == 404:
            pytest.xfail(f"{path} not implemented yet")
        assert error_code(response) != "CONSENT_REQUIRED", (
            f"{path} is behind the consent gate — a user who has not consented can never "
            "reach the screen that lets them consent, nor withdraw or export their data"
        )

    async def test_data_export_is_reachable_without_consent(
        self, api_app, consentless_client
    ) -> None:
        """RGPD Art. 15/20 do not depend on having accepted the terms."""
        response = await consentless_client.post("/api/v1/me/data-export")
        if response.status_code == 404:
            pytest.xfail("/me/data-export not implemented yet")
        assert error_code(response) != "CONSENT_REQUIRED"

    async def test_account_deletion_is_reachable_without_consent(
        self, api_app, consentless_client
    ) -> None:
        """Art. 17. Blocking erasure behind consent would be the worst possible gate."""
        response = await consentless_client.post("/api/v1/me/delete-account")
        if response.status_code == 404:
            pytest.xfail("/me/delete-account not implemented yet")
        assert error_code(response) != "CONSENT_REQUIRED"


class TestPartialConsent:
    """All three mandatory consents are required — any missing one blocks."""

    @pytest.mark.parametrize("missing", ["tos", "privacy", "health_data"])
    async def test_one_missing_mandatory_consent_still_blocks(
        self, api_app, deps_module, client, missing: str
    ) -> None:
        get_current_user = getattr(deps_module, "get_current_user", None)
        if get_current_user is None:
            pytest.xfail("app.core.deps.get_current_user not available yet")

        factory = require("tests.support.factories", "user_with_consents_except")
        api_app.dependency_overrides[get_current_user] = lambda: factory(missing)
        try:
            routes = _business_routes(api_app)
            if not routes:
                pytest.xfail("no business routes yet")
            method, path = routes[0]
            response = await client.request(method, _concretise(path))
            assert error_code(response) == "CONSENT_REQUIRED", (
                f"missing {missing!r} consent did not block a business route"
            )
        finally:
            api_app.dependency_overrides.clear()

    async def test_optional_consents_do_not_block(self, api_app, deps_module, client) -> None:
        """``progress_photos`` and ``marketing`` are opt-in and must never gate the app.

        ``marketing`` especially: making the product unusable until the user accepts
        marketing would be consent obtained under duress, which is not consent.
        """
        get_current_user = getattr(deps_module, "get_current_user", None)
        if get_current_user is None:
            pytest.xfail("app.core.deps.get_current_user not available yet")

        factory = require("tests.support.factories", "fully_consented_user")
        api_app.dependency_overrides[get_current_user] = lambda: factory()
        try:
            routes = _business_routes(api_app)
            if not routes:
                pytest.xfail("no business routes yet")
            blocked = []
            for method, path in routes:
                response = await client.request(method, _concretise(path))
                if error_code(response) == "CONSENT_REQUIRED":
                    blocked.append(f"{method} {path}")
            assert not blocked, (
                "routes still demanding consent from a fully-consented user "
                "(mandatory granted, optional declined):\n" + "\n".join(blocked)
            )
        finally:
            api_app.dependency_overrides.clear()
