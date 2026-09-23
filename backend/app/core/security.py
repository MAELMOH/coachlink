"""Password hashing (Argon2id) and JWT issuance/verification.

Access token: 15 minutes, stateless.
Refresh token: 30 days, rotating and revocable — only a SHA-256 digest of it is
stored, so a database dump does not hand over live sessions.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings, get_settings
from app.core.errors import ApiError, ErrorCode

__all__ = [
    "TokenPayload",
    "create_access_token",
    "decode_token",
    "generate_invitation_code",
    "generate_refresh_token",
    "hash_password",
    "hash_refresh_token",
    "needs_rehash",
    "verify_password",
]

#: Unambiguous alphabet for invitation codes: no O/0, no I/1/l.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _hasher(settings: Settings | None = None) -> PasswordHasher:
    cfg = settings or get_settings()
    return PasswordHasher(
        time_cost=cfg.argon2_time_cost,
        memory_cost=cfg.argon2_memory_cost_kib,
        parallelism=cfg.argon2_parallelism,
        hash_len=32,
        salt_len=16,
    )


def hash_password(password: str, settings: Settings | None = None) -> str:
    return _hasher(settings).hash(password)


def verify_password(password: str, password_hash: str, settings: Settings | None = None) -> bool:
    try:
        return _hasher(settings).verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str, settings: Settings | None = None) -> bool:
    """True when the stored hash predates a parameter bump — rehash on next login."""
    try:
        return _hasher(settings).check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


class TokenPayload:
    """Decoded access-token claims."""

    __slots__ = ("expires_at", "jti", "role", "user_id")

    def __init__(self, user_id: UUID, role: str, expires_at: datetime, jti: str) -> None:
        self.user_id = user_id
        self.role = role
        self.expires_at = expires_at
        self.jti = jti


def create_access_token(
    user_id: UUID,
    role: str,
    *,
    now: datetime,
    settings: Settings | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    cfg = settings or get_settings()
    expires = now + timedelta(minutes=cfg.access_token_ttl_minutes)
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(claims, cfg.jwt_secret.get_secret_value(), algorithm=cfg.jwt_algorithm)


def decode_token(
    token: str,
    *,
    expected_type: Literal["access", "refresh"] = "access",
    settings: Settings | None = None,
) -> TokenPayload:
    """Decode and validate. Raises :class:`ApiError` with a stable error code."""
    cfg = settings or get_settings()
    try:
        claims = jwt.decode(
            token,
            cfg.jwt_secret.get_secret_value(),
            algorithms=[cfg.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(ErrorCode.TOKEN_EXPIRED, "Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise ApiError(ErrorCode.TOKEN_INVALID, "Invalid token.") from exc

    if claims.get("typ") != expected_type:
        raise ApiError(ErrorCode.TOKEN_INVALID, "Unexpected token type.")

    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise ApiError(ErrorCode.TOKEN_INVALID, "Invalid token subject.") from exc

    return TokenPayload(
        user_id=user_id,
        role=str(claims.get("role", "")),
        expires_at=datetime.fromtimestamp(int(claims["exp"]), tz=UTC),
        jti=str(claims.get("jti", "")),
    )


def generate_refresh_token() -> str:
    """Opaque, high-entropy refresh token. Never a JWT: it must be revocable."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """SHA-256 of the token — what actually gets stored.

    Argon2 would be wrong here: the input already has 384 bits of entropy, so
    there is nothing to brute-force, and login latency matters.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def generate_invitation_code(length: int = 8) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))
