"""Pydantic contract for `/auth/*` (ARCHITECTURE.md §8).

These models *are* the API documentation: `front` generates the Dart classes from the
OpenAPI document they produce, so field names and optionality are a shared contract,
not an implementation detail.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.domain.enums import UserRole

__all__ = [
    "LoginRequest",
    "LogoutRequest",
    "RefreshRequest",
    "RegisterRequest",
    "TokenPair",
    "UserPublic",
]

#: Argon2id handles long inputs fine, but an unbounded password is a cheap DoS:
#: hashing is deliberately expensive. 128 characters is far beyond any real passphrase.
MAX_PASSWORD_LENGTH = 128
MIN_PASSWORD_LENGTH = 10


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    role: UserRole
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    #: IANA name. "Today's session" is computed in the user's timezone, never in UTC
    #: (ARCHITECTURE.md §4), so the mobile app sends the device timezone at signup.
    timezone: str = Field(default="Europe/Paris", max_length=64)
    locale: str = Field(default="fr", max_length=10)
    #: Required for clients only: under-16 signup is refused (§5.2). A coach's birth
    #: date is not needed, so we do not collect it — data minimisation.
    birth_date: date | None = None

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        # Stored in a citext column, but normalising here keeps what we echo back
        # identical to what a later login will match.
        return value.strip().lower()

    @field_validator("first_name", "last_name")
    @classmethod
    def _strip_names(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)
    #: Refreshed at every login: users travel, and a stale timezone silently shifts
    #: which day "today's session" refers to.
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        return value.strip().lower()


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=16, max_length=512)


class LogoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=16, max_length=512)
    #: Log out of every device rather than just this one.
    all_sessions: bool = False


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: UserRole
    first_name: str
    last_name: str
    locale: str
    timezone: str
    created_at: datetime


class TokenPair(BaseModel):
    """Access token is a JWT; refresh token is opaque and revocable, never a JWT."""

    access_token: str
    refresh_token: str
    # S105 flags the name, not the value: "bearer" is the RFC 6750 scheme name that
    # goes in the Authorization header, not a credential.
    token_type: str = "bearer"  # noqa: S105
    expires_in: int = Field(description="Access-token lifetime in seconds.")
    user: UserPublic
