"""HTTP middleware: request id, structured access log, rate limiting.

Access logs carry a request id and a pseudonymised user id — never a path
parameter that could be an identifier, never a body, never a header value.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.core.logging import get_logger, pseudonymize
from app.core.ratelimit import RateLimiter

__all__ = ["REQUEST_ID_HEADER", "RateLimitMiddleware", "RequestContextMiddleware"]

REQUEST_ID_HEADER = "X-Request-ID"

log = get_logger(__name__)

#: Routes whose path itself is sensitive enough that we log only the route
#: template, never the resolved path.
_SENSITIVE_PREFIXES = ("/api/v1/measurements", "/api/v1/progress-photos", "/api/v1/conversations")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, binds it to structlog contextvars, times the call."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            log.exception(
                "request.failed",
                method=request.method,
                route=_safe_route(request),
                duration_ms=duration_ms,
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        user_id = getattr(request.state, "user_id", None)
        log.info(
            "request.completed",
            method=request.method,
            route=_safe_route(request),
            status=response.status_code,
            duration_ms=duration_ms,
            # Pseudonymised: correlatable across requests, not re-identifiable.
            actor=pseudonymize(str(user_id)) if user_id else None,
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def _safe_route(request: Request) -> str:
    """Route template when available, so ids in the path never reach the logs."""
    route = request.scope.get("route")
    path_format = getattr(route, "path_format", None) or getattr(route, "path", None)
    if path_format:
        return str(path_format)
    path = request.url.path
    for prefix in _SENSITIVE_PREFIXES:
        if path.startswith(prefix):
            return f"{prefix}/*"
    return path


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window limiter: 100 req/min per user, 5/min on /auth/login (§8).

    Keyed on the authenticated user when available, otherwise on a hashed client
    IP — the raw address is never used as a key, and never stored.
    """

    def __init__(self, app: ASGIApp, limiter: RateLimiter, settings: Settings) -> None:
        super().__init__(app)
        self._limiter = limiter
        self._settings = settings

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not self._settings.rate_limit_enabled or request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if path in ("/health", "/health/live", "/health/ready"):
            return await call_next(request)

        if path.endswith("/auth/login"):
            bucket, limit = "login", self._settings.login_rate_limit_per_minute
        else:
            bucket, limit = "api", self._settings.rate_limit_per_minute

        identity = self._identity(request)
        allowed, retry_after = await self._limiter.check(
            f"{bucket}:{identity}", limit=limit, window_seconds=60
        )
        if not allowed:
            err = ApiError(
                ErrorCode.RATE_LIMITED,
                "Too many requests. Please retry shortly.",
                details={"retry_after_seconds": retry_after},
            )
            return JSONResponse(
                status_code=err.status_code,
                content=err.to_payload(),
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)

    def _identity(self, request: Request) -> str:
        from app.core.logging import hash_ip

        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return f"u:{user_id}"
        # Authorization header is a good pre-auth proxy for "same caller".
        auth = request.headers.get("authorization")
        if auth:
            return f"t:{pseudonymize(auth)}"
        client = request.client.host if request.client else None
        return f"ip:{hash_ip(client) or 'unknown'}"
