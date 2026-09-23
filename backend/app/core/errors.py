"""Normalised API errors.

Wire format (ARCHITECTURE.md §8)::

    {"error": {"code": "CONSENT_REQUIRED", "message": "...", "details": {...}}}

``code`` is the stable contract: clients and tests branch on it, never on ``message``
(which is human-facing and translatable). Adding a code is fine; renaming one is a
breaking API change.
"""

from __future__ import annotations

from typing import Any

__all__ = ["ApiError", "ErrorCode", "http_status_for"]


class ErrorCode:
    """Frozen error-code vocabulary. Referenced by the mobile app and the QA suite."""

    # --- auth -------------------------------------------------------------
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_INVALID = "TOKEN_INVALID"
    TOKEN_REVOKED = "TOKEN_REVOKED"
    NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
    EMAIL_ALREADY_USED = "EMAIL_ALREADY_USED"
    UNDERAGE = "UNDERAGE"

    # --- authorisation / isolation (risk #1) ------------------------------
    FORBIDDEN = "FORBIDDEN"
    NO_ACTIVE_LINK = "NO_ACTIVE_LINK"
    LINK_PAUSED = "LINK_PAUSED"
    LINK_REVOKED = "LINK_REVOKED"
    WRONG_ROLE = "WRONG_ROLE"

    # --- RGPD -------------------------------------------------------------
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    PHOTO_NOT_SHARED = "PHOTO_NOT_SHARED"

    # --- billing ----------------------------------------------------------
    TRIAL_EXPIRED = "TRIAL_EXPIRED"
    SUBSCRIPTION_REQUIRED = "SUBSCRIPTION_REQUIRED"
    READ_ONLY_MODE = "READ_ONLY_MODE"

    # --- feature gating ---------------------------------------------------
    MESSAGING_DISABLED = "MESSAGING_DISABLED"
    NUTRITION_DISABLED = "NUTRITION_DISABLED"

    # --- generic ----------------------------------------------------------
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    IDEMPOTENCY_KEY_REQUIRED = "IDEMPOTENCY_KEY_REQUIRED"
    IDEMPOTENCY_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED"
    INVITATION_INVALID = "INVITATION_INVALID"
    INVITATION_EXPIRED = "INVITATION_EXPIRED"
    INVITATION_CONSUMED = "INVITATION_CONSUMED"
    RATE_LIMITED = "RATE_LIMITED"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA = "UNSUPPORTED_MEDIA"
    INTERNAL_ERROR = "INTERNAL_ERROR"


#: Default HTTP status per code. Handlers may override with an explicit status.
_STATUS: dict[str, int] = {
    ErrorCode.INVALID_CREDENTIALS: 401,
    ErrorCode.TOKEN_EXPIRED: 401,
    ErrorCode.TOKEN_INVALID: 401,
    ErrorCode.TOKEN_REVOKED: 401,
    ErrorCode.NOT_AUTHENTICATED: 401,
    ErrorCode.EMAIL_ALREADY_USED: 409,
    ErrorCode.UNDERAGE: 422,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NO_ACTIVE_LINK: 403,
    ErrorCode.LINK_PAUSED: 403,
    ErrorCode.LINK_REVOKED: 403,
    ErrorCode.WRONG_ROLE: 403,
    ErrorCode.CONSENT_REQUIRED: 403,
    ErrorCode.PHOTO_NOT_SHARED: 403,
    ErrorCode.TRIAL_EXPIRED: 402,
    ErrorCode.SUBSCRIPTION_REQUIRED: 402,
    ErrorCode.READ_ONLY_MODE: 403,
    ErrorCode.MESSAGING_DISABLED: 409,
    ErrorCode.NUTRITION_DISABLED: 409,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.IDEMPOTENCY_KEY_REQUIRED: 400,
    ErrorCode.IDEMPOTENCY_KEY_REUSED: 409,
    ErrorCode.INVITATION_INVALID: 404,
    ErrorCode.INVITATION_EXPIRED: 410,
    ErrorCode.INVITATION_CONSUMED: 409,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.PAYLOAD_TOO_LARGE: 413,
    ErrorCode.UNSUPPORTED_MEDIA: 415,
    ErrorCode.INTERNAL_ERROR: 500,
}


def http_status_for(code: str, default: int = 400) -> int:
    return _STATUS.get(code, default)


class ApiError(Exception):
    """Raise this anywhere; the global handler renders the normalised envelope.

    ``details`` must never carry PII — it ends up in logs and in Sentry.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code if status_code is not None else http_status_for(code)
        self.details = details or {}

    def to_payload(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}
