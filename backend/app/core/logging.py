"""structlog configuration — PII-free by construction (ARCHITECTURE.md §5.4).

Two safeguards rather than good intentions:

1. :func:`pseudonymize` turns any identifier into a short HMAC digest, so logs
   correlate without carrying an email, a name or a raw user id.
2. :func:`scrub_pii` is a structlog processor that *drops* known-sensitive keys
   from every event, wherever in the codebase they were passed. A developer
   logging ``weight_kg=...`` by accident gets ``[redacted]``, not a data leak.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import sys
from typing import Any

import structlog

from app.core.config import get_settings

__all__ = ["configure_logging", "get_logger", "pseudonymize", "hash_ip", "scrub_pii"]

#: Keys never written to logs, whatever their value. Checked case-insensitively
#: on the exact key name. Keep alphabetical, add freely — over-redacting is cheap.
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "access_token",
        "arm_cm",
        "attachment_key",
        "authorization",
        "birth_date",
        "body",
        "body_fat_pct",
        "carbs_g",
        "chest_cm",
        "client_notes",
        "coach_notes",
        "comment",
        "cookie",
        "dek",
        "description",
        "email",
        "email_hint",
        "fat_g",
        "first_name",
        "goal",
        "height_cm",
        "hip_cm",
        "ip",
        "ip_address",
        "kcal",
        "kcal_target",
        "kek",
        "last_name",
        "macros",
        "message",
        "password",
        "password_hash",
        "payload",
        "phone",
        "protein_g",
        "refresh_token",
        "remote_addr",
        "secret",
        "set-cookie",
        "storage_key",
        "thigh_cm",
        "token",
        "waist_cm",
        "weight_kg",
    }
)

_REDACTED = "[redacted]"


def scrub_pii(
    _logger: object, _name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Drop sensitive keys from the event, recursively into nested dicts."""
    return _scrub(event_dict)


def _scrub(value: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in value.items():
        if key.lower() in SENSITIVE_KEYS:
            out[key] = _REDACTED
        elif isinstance(val, dict):
            out[key] = _scrub(val)
        else:
            out[key] = val
    return out


def _log_secret() -> bytes:
    return get_settings().jwt_secret.get_secret_value().encode()


def pseudonymize(value: str | None, *, length: int = 12) -> str | None:
    """Stable, non-reversible pseudonym for an identifier (user id, email...).

    Same input always yields the same pseudonym, so traces stay correlatable,
    but the original value cannot be recovered from the logs.
    """
    if value is None:
        return None
    digest = hmac.new(_log_secret(), str(value).encode(), hashlib.sha256).hexdigest()
    return digest[:length]


def hash_ip(ip: str | None) -> str | None:
    """Hashed IP for the `consent.ip_hash` / `audit_log.ip_hash` columns."""
    if not ip:
        return None
    return hmac.new(_log_secret(), ip.encode(), hashlib.sha256).hexdigest()


def configure_logging() -> None:
    settings = get_settings()

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        scrub_pii,  # must run before any renderer
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)
