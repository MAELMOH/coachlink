"""FastAPI application factory.

``create_app()`` rather than a module-level ``app`` so the test suite can build a
fresh instance per test with its own ``dependency_overrides``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api.consent_gate import assert_consent_gate_complete
from app.api.errors import register_exception_handlers
from app.api.v1 import api_router
from app.core.config import Settings, get_settings
from app.core.db import dispose_engine
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RateLimitMiddleware, RequestContextMiddleware
from app.core.ratelimit import InMemoryRateLimiter, RateLimiter, RedisRateLimiter

__all__ = ["app", "create_app"]

log = get_logger(__name__)

DESCRIPTION = """
API of **CoachLink** — connects a sports coach with their clients.

Conventions (see `ARCHITECTURE.md` §8):
* JSON, `snake_case`, dates in **ISO-8601 UTC**.
* Errors: `{"error": {"code": "...", "message": "...", "details": {}}}` — branch on `code`.
* Cursor pagination: `?cursor=&limit=` → `{"items": [], "next_cursor": null}`.
* `Idempotency-Key` header required on `POST /workout-logs` and billing routes.
* Bearer JWT: access token valid 15 minutes, refreshed via `POST /auth/refresh`.

A coach can only ever read a client's data through an **active** `coach_client_link`.
"""


def _build_rate_limiter(settings: Settings) -> RateLimiter:
    try:
        return RedisRateLimiter(Redis.from_url(settings.redis_url, decode_responses=True))
    except Exception:
        if settings.is_production:
            raise
        log.warning("ratelimit.redis_unavailable", fallback="in_memory")
        return InMemoryRateLimiter()


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        log.info("app.startup", environment=cfg.environment)
        yield
        await dispose_engine()
        log.info("app.shutdown")

    app = FastAPI(
        title=cfg.project_name,
        description=DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
        # OpenAPI is exposed in dev/test only — `front` generates the Dart models
        # from it (§8). Never exposed in staging/prod.
        openapi_url="/openapi.json" if cfg.expose_openapi else None,
        docs_url="/docs" if cfg.expose_openapi else None,
        redoc_url="/redoc" if cfg.expose_openapi else None,
        separate_input_output_schemas=False,
    )

    app.add_middleware(RateLimitMiddleware, limiter=_build_rate_limiter(cfg), settings=cfg)
    app.add_middleware(RequestContextMiddleware)

    if cfg.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cfg.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )

    register_exception_handlers(app)

    app.include_router(api_router, prefix=cfg.api_v1_prefix)
    # Probes live outside /api/v1: orchestrators should not care about API versions.
    from app.api.v1.health import router as health_router

    app.include_router(health_router)

    # Deny-by-default consent gate (§5.2). Raises if any route is neither exempt nor
    # gated, so "somebody forgot the dependency" is a startup crash naming the routes
    # rather than a silent data-protection incident in production.
    assert_consent_gate_complete(app)

    return app


app = create_app()
