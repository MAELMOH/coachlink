"""Pydantic contract for invitations and the coach↔client link."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domain.enums import CoachingMode, LinkStatus

__all__ = [
    "ClientSummary",
    "ClientsPage",
    "InvitationCreateRequest",
    "InvitationPublic",
    "LinkPublic",
    "LinkUpdateRequest",
]


class InvitationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coaching_mode: CoachingMode
    #: Purely a reminder for the coach ("who did I send this to?"). Never used to
    #: authenticate the redeemer — the code alone does that.
    email_hint: EmailStr | None = None


class InvitationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    coaching_mode: CoachingMode
    email_hint: str | None
    expires_at: datetime
    consumed_at: datetime | None
    created_at: datetime

    @property
    def is_usable(self) -> bool:  # pragma: no cover - convenience for the mobile app
        return self.consumed_at is None


class LinkPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    coach_id: UUID
    client_id: UUID
    status: LinkStatus
    coaching_mode: CoachingMode
    started_at: datetime | None
    ended_at: datetime | None


class LinkUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: LinkStatus


class ClientSummary(BaseModel):
    """One row of the coach's multi-client dashboard.

    Carries identity and relationship state only — no measurement, no photo, no
    health data. The dashboard is a list, and a list must not become a bulk export
    of everybody's sensitive columns.
    """

    link_id: UUID
    client_id: UUID
    first_name: str
    last_name: str
    status: LinkStatus
    coaching_mode: CoachingMode
    started_at: datetime | None


class ClientsPage(BaseModel):
    """Cursor pagination (ARCHITECTURE.md §8)."""

    items: list[ClientSummary]
    next_cursor: str | None = Field(
        default=None, description="Pass back as ?cursor= to fetch the next page."
    )
