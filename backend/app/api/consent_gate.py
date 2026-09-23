"""The blocking consent gate (ARCHITECTURE.md §5.2), enforced as a whitelist.

    « Bloquant : tant que ``tos``, ``privacy`` et ``health_data`` ne sont pas accordés,
    l'API renvoie ``403 CONSENT_REQUIRED`` sur toute route métier. »

**"Toute route métier"** is the hard part. A gate covering 90% of routes is not a gate:
the one route that slips through processes health data with no legal basis, and it will
be the route someone adds last, in a hurry, without the dependency.

So forgetting it is made impossible rather than merely discouraged:

* business routers declare ``dependencies=[Depends(require_consent)]`` once, at the
  router level, so individual endpoints cannot each forget it;
* :func:`assert_consent_gate_complete` runs at the end of ``create_app()`` and **refuses
  to build the application** if any route is neither exempt nor gated.

That second half is what makes this a whitelist. A new router added without the
dependency does not leak quietly in production — the process fails to start, in
development, on the first run, with the offending routes named.

What is deliberately NOT gated, and why
---------------------------------------
``/me``, ``/me/consents``, ``/me/data-export`` and ``/me/delete-account`` stay reachable
without consent. A user who has not consented must still be able to *grant* consent, and
GDPR Art. 15/17/20 (access, erasure, portability) do not depend on having accepted the
terms. A gate covering those would make consent impossible to give and impossible to
withdraw — the worst possible failure mode, and a far more likely one than it sounds,
since "gate everything" is the intuitive implementation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy import select

from app.core.deps import CurrentUser, SessionDep
from app.core.errors import ApiError, ErrorCode
from app.domain.consent import missing_mandatory_consents
from app.domain.enums import ConsentPurpose
from app.models.compliance import Consent

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = [
    "CONSENT_EXEMPT_EXACT",
    "CONSENT_EXEMPT_PREFIXES",
    "ConsentGateError",
    "assert_consent_gate_complete",
    "granted_consents_for",
    "is_exempt",
    "iter_effective_routes",
    "require_consent",
]

#: Exact paths reachable without the mandatory consents. Kept in sync with the QA
#: sweep in ``tests/integration/test_consent_gate.py`` — if the two ever disagree,
#: that suite fails, which is the point.
CONSENT_EXEMPT_EXACT: frozenset[str] = frozenset(
    {
        "/health",
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

#: Whole subtrees that must stay open: you cannot log in if logging in needs consent,
#: and a billing webhook is not a user.
CONSENT_EXEMPT_PREFIXES: tuple[str, ...] = ("/api/v1/auth/", "/webhooks/")


class ConsentGateError(RuntimeError):
    """Raised at startup when a route is neither exempt nor gated."""


def is_exempt(path: str) -> bool:
    return path in CONSENT_EXEMPT_EXACT or path.startswith(CONSENT_EXEMPT_PREFIXES)


def iter_effective_routes(app: FastAPI) -> list[tuple[str, frozenset[str], list[object]]]:
    """Every *real* endpoint of ``app`` as ``(full_path, methods, dependencies)``.

    Walking ``app.routes`` directly is wrong on FastAPI ≥ 0.13x: ``include_router`` no
    longer copies the child routes in, it stores a lazy ``_IncludedRouter`` placeholder
    and flattens on demand. Iterating ``app.routes`` therefore yields the placeholders
    and **misses every mounted endpoint** — a route sweep written that way silently
    inspects nothing and reports success.

    ``fastapi.routing.iter_route_contexts`` is the same helper FastAPI uses to build its
    own OpenAPI document, so it resolves full paths and the dependencies inherited from
    each router exactly as the request path does.
    """
    from fastapi import routing as fastapi_routing

    effective: list[tuple[str, frozenset[str], list[object]]] = []
    for context in fastapi_routing.iter_route_contexts(app.routes):
        methods = getattr(context, "methods", None)
        path = getattr(context, "path", None)
        if not path or not methods:
            continue
        dependencies = getattr(getattr(context.route, "dependant", None), "dependencies", [])
        effective.append((path, frozenset(methods), list(dependencies)))
    return effective


async def granted_consents_for(user: object, session: SessionDep) -> frozenset[ConsentPurpose]:
    """Purposes currently granted by ``user``.

    Reads ``user.granted_consents`` when the caller has already resolved them (an eager
    load, a cache, or a test double injected through ``dependency_overrides``) and falls
    back to the ``consent`` table otherwise. Checking the in-memory value first is also
    what keeps the gate from touching the database at all on the refusal path.

    A purpose counts as granted only on its most recent row: consent is revocable, so an
    old ``granted=true`` followed by a revocation must not keep the gate open.
    """
    cached = getattr(user, "granted_consents", None)
    if cached is not None:
        return frozenset(cached)

    user_id = getattr(user, "id", None)
    if user_id is None:  # pragma: no cover - defensive
        return frozenset()

    rows = await session.execute(
        select(Consent.purpose, Consent.granted, Consent.revoked_at)
        .where(Consent.user_id == user_id)
        .order_by(Consent.purpose, Consent.created_at.desc())
    )
    latest: dict[str, bool] = {}
    for purpose, granted, revoked_at in rows:
        # Ordered newest-first per purpose, so the first row wins.
        if purpose in latest:
            continue
        latest[purpose] = bool(granted) and revoked_at is None
    return frozenset(
        ConsentPurpose(purpose) for purpose, is_granted in latest.items() if is_granted
    )


async def require_consent(user: CurrentUser, session: SessionDep) -> None:
    """Refuse the request while a mandatory consent is missing.

    ``details`` lists the missing purposes so the mobile app can open the right screen.
    Purposes are a closed vocabulary, not personal data, so they are safe to log.
    """
    granted = await granted_consents_for(user, session)
    missing = missing_mandatory_consents(granted)
    if missing:
        raise ApiError(
            ErrorCode.CONSENT_REQUIRED,
            "Mandatory consents are missing.",
            details={"missing": sorted(str(purpose) for purpose in missing)},
        )


#: The dependency business routers must carry. Compared by identity at startup.
ConsentGate = Depends(require_consent)


def assert_consent_gate_complete(app: FastAPI) -> None:
    """Fail fast when a route is neither exempt nor behind :func:`require_consent`.

    Called from ``create_app()``. Raising here turns "somebody forgot the dependency"
    from a silent production data-protection incident into a startup crash naming the
    routes, on the machine of whoever added them.
    """
    ungated: list[str] = []
    for path, methods, dependencies in iter_effective_routes(app):
        if is_exempt(path):
            continue
        if not any(getattr(dep, "call", None) is require_consent for dep in dependencies):
            for method in sorted(methods - {"HEAD", "OPTIONS"}):
                ungated.append(f"{method} {path}")

    if ungated:
        raise ConsentGateError(
            "these routes are neither exempt nor behind require_consent, so they would "
            "process personal data without a legal basis (ARCHITECTURE.md §5.2):\n"
            + "\n".join(f"  {route}" for route in sorted(ungated))
            + "\n\nAdd `dependencies=[Depends(require_consent)]` to the router, or add the "
            "path to CONSENT_EXEMPT_EXACT / CONSENT_EXEMPT_PREFIXES with a written reason."
        )
