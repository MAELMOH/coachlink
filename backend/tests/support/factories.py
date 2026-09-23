"""Test data builders.

Deliberately plain objects rather than ``factory_boy``: what the suite needs is a handful
of readable, explicit shapes, and a stub returned from ``dependency_overrides`` does not
have to be a SQLAlchemy instance. The DB-backed factories arrive in the same file once
``back`` lands ``app/models`` — the call sites below will not have to change.

Every builder states the *intent* in its name (``consentless_user``), never the mechanics,
so a test reads as the scenario it describes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.domain.enums import (
    CoachingMode,
    ConsentPurpose,
    LinkStatus,
    UserRole,
)
from app.domain.ids import uuid7

__all__ = [
    "LinkStub",
    "UserStub",
    "active_link",
    "client_user",
    "coach",
    "consentless_user",
    "fully_consented_user",
    "link_with_status",
    "user_with_consents_except",
]

MANDATORY = (ConsentPurpose.TOS, ConsentPurpose.PRIVACY, ConsentPurpose.HEALTH_DATA)


REFERENCE_NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


@dataclass
class UserStub:
    """Stand-in for the authenticated principal.

    Carries every field ``app.schemas.auth.UserPublic`` serialises. That is not padding:
    a stub missing ``locale``/``timezone``/``created_at`` makes ``GET /me`` raise a
    Pydantic validation error, and the test then fails for the shape of the double
    rather than for the behaviour under test — which is exactly the kind of noise that
    gets a real failure dismissed as "just the fixture".
    """

    id: UUID = field(default_factory=uuid7)
    role: UserRole = UserRole.CLIENT
    email: str = "user@coachlink.test"
    first_name: str = "Test"
    last_name: str = "User"
    locale: str = "fr"
    timezone: str = "Europe/Paris"
    created_at: datetime = REFERENCE_NOW
    granted_consents: frozenset[ConsentPurpose] = frozenset()
    trial_ends_at: datetime | None = None
    deleted_at: datetime | None = None

    def has_all_mandatory_consents(self) -> bool:
        return all(purpose in self.granted_consents for purpose in MANDATORY)


@dataclass
class LinkStub:
    id: UUID = field(default_factory=uuid7)
    coach_id: UUID = field(default_factory=uuid7)
    client_id: UUID = field(default_factory=uuid7)
    status: LinkStatus = LinkStatus.ACTIVE
    coaching_mode: CoachingMode = CoachingMode.DISTANCE
    started_at: datetime = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    ended_at: datetime | None = None


# ---------------------------------------------------------------------------
# Consent states — the three the gate must distinguish
# ---------------------------------------------------------------------------


def consentless_user(role: UserRole = UserRole.CLIENT) -> UserStub:
    """Freshly registered: authenticated, but has granted nothing.

    The state every business route must refuse with 403 CONSENT_REQUIRED.
    """
    return UserStub(role=role, granted_consents=frozenset())


def fully_consented_user(role: UserRole = UserRole.CLIENT) -> UserStub:
    """Mandatory consents granted, optional ones declined.

    Optional-declined is the *default* real-world state (``marketing`` is opt-in and
    unchecked per §5.2), so it is what "normal user" means in this suite — using an
    all-consents user as the baseline would hide a gate that wrongly requires an optional
    consent.
    """
    return UserStub(role=role, granted_consents=frozenset(MANDATORY))


def user_with_consents_except(missing: str | ConsentPurpose) -> UserStub:
    """All mandatory consents but one — proves the gate needs *all three*."""
    missing_purpose = ConsentPurpose(missing)
    return UserStub(granted_consents=frozenset(p for p in MANDATORY if p is not missing_purpose))


# ---------------------------------------------------------------------------
# Actors and links
# ---------------------------------------------------------------------------


def coach(**overrides) -> UserStub:
    base = {
        "role": UserRole.COACH,
        "email": f"coach-{uuid7().hex[:8]}@coachlink.test",
        "granted_consents": frozenset(MANDATORY),
    }
    return UserStub(**{**base, **overrides})


def client_user(*, in_trial: bool = True, **overrides) -> UserStub:
    now = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    base = {
        "role": UserRole.CLIENT,
        "email": f"client-{uuid7().hex[:8]}@coachlink.test",
        "granted_consents": frozenset(MANDATORY),
        "trial_ends_at": now + timedelta(days=10) if in_trial else now - timedelta(days=1),
    }
    return UserStub(**{**base, **overrides})


def active_link(coach_user: UserStub, client: UserStub, **overrides) -> LinkStub:
    return LinkStub(
        coach_id=coach_user.id,
        client_id=client.id,
        status=LinkStatus.ACTIVE,
        **overrides,
    )


def link_with_status(
    coach_user: UserStub, client: UserStub, status: LinkStatus, **overrides
) -> LinkStub:
    """``paused`` / ``revoked`` / ``pending`` — each must cut coach access."""
    return LinkStub(coach_id=coach_user.id, client_id=client.id, status=status, **overrides)
