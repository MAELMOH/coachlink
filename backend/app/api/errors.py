"""Exception handlers rendering the normalised error envelope (§8).

Every error leaving the API — ours, FastAPI's validation errors, and unexpected
crashes — uses the same shape, so the mobile client has exactly one parser.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.core.errors import ApiError, ErrorCode
from app.core.logging import get_logger
from app.core.middleware import REQUEST_ID_HEADER

__all__ = ["register_exception_handlers"]

log = get_logger(__name__)

_STATUS_TO_CODE = {
    401: ErrorCode.NOT_AUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_MEDIA,
    429: ErrorCode.RATE_LIMITED,
}


def _envelope(
    request: Request, status: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    payload = {"error": {"code": code, "message": message, "details": details or {}}}
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(status_code=status, content=payload, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _envelope(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Report field locations and error types, never the rejected *values*:
        # a failing password or weight would otherwise end up in logs and Sentry.
        fields = [
            {"loc": [str(p) for p in err.get("loc", [])], "type": err.get("type", "invalid")}
            for err in exc.errors()
        ]
        return _envelope(
            request,
            422,
            ErrorCode.VALIDATION_ERROR,
            "Request payload is invalid.",
            {"fields": fields},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return _envelope(request, exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Log the traceback server-side; return nothing about it to the caller.
        log.exception("unhandled_exception", exc_type=type(exc).__name__)
        return _envelope(request, 500, ErrorCode.INTERNAL_ERROR, "An unexpected error occurred.")
