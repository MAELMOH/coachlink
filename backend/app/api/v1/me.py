"""`/me` — the account's own view of itself, and its consents.

**Deliberately outside the consent gate** (ARCHITECTURE.md §5.2, §5.3). A user who has
granted nothing must still be able to reach the screen that lets them grant, withdraw,
export or erase. A gate covering these routes would make consent impossible to give and
impossible to take back — over-blocking is as much a GDPR failure as under-blocking.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.consent_gate import granted_consents_for
from app.core.deps import ClockDep, CurrentUser, SessionDep, SettingsDep
from app.domain.consent import is_mandatory, missing_mandatory_consents
from app.domain.enums import OPTIONAL_CONSENTS, REQUIRED_CONSENTS, ConsentPurpose
from app.domain.ids import uuid7
from app.models.compliance import Consent
from app.schemas.auth import UserPublic
from app.services.audit import hash_ip

router = APIRouter(prefix="/me", tags=["me"])

#: Bumped whenever the wording of the terms or privacy policy changes. A consent is
#: proof only if it records *which version* was accepted, so this is stored per row.
CONSENT_DOCUMENT_VERSION = "2026-09-1"


class ConsentState(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    purpose: ConsentPurpose
    granted: bool
    mandatory: bool
    version: str | None = None
    granted_at: datetime | None = None
    revoked_at: datetime | None = None


class ConsentsResponse(BaseModel):
    items: list[ConsentState]
    #: Empty means every business route is reachable.
    missing_mandatory: list[ConsentPurpose]


class ConsentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: ConsentPurpose
    granted: bool


class ConsentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[ConsentDecision] = Field(min_length=1, max_length=len(ConsentPurpose))


@router.get("", summary="The authenticated account", response_model=UserPublic)
async def read_me(user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(user)


@router.get("/consents", summary="Consent state per purpose", response_model=ConsentsResponse)
async def read_consents(user: CurrentUser, session: SessionDep) -> ConsentsResponse:
    granted = await granted_consents_for(user, session)

    rows = list(
        await session.scalars(
            select(Consent).where(Consent.user_id == user.id).order_by(Consent.created_at.desc())
        )
    )
    latest: dict[str, Consent] = {}
    for row in rows:
        latest.setdefault(str(row.purpose), row)

    items = []
    for purpose in list(REQUIRED_CONSENTS) + list(OPTIONAL_CONSENTS):
        row = latest.get(str(purpose))
        items.append(
            ConsentState(
                purpose=purpose,
                granted=purpose in granted,
                mandatory=is_mandatory(purpose),
                version=row.version if row else None,
                granted_at=row.granted_at if row else None,
                revoked_at=row.revoked_at if row else None,
            )
        )

    return ConsentsResponse(
        items=sorted(items, key=lambda item: (not item.mandatory, item.purpose)),
        missing_mandatory=sorted(missing_mandatory_consents(granted)),
    )


@router.post("/consents", summary="Grant or withdraw consents", response_model=ConsentsResponse)
async def update_consents(
    payload: ConsentUpdateRequest,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> ConsentsResponse:
    """Append one row per decision.

    Rows are **never updated in place**: the history is the compliance evidence. Proving
    "this user accepted version X on date Y, then withdrew on date Z" is only possible
    if both events survive, and a regulator asks for exactly that.
    """
    now = clock.now()
    client = request.client
    ip_hash = hash_ip(getattr(client, "host", None), salt=settings.jwt_secret.get_secret_value())
    user_agent = request.headers.get("user-agent")

    for decision in payload.decisions:
        session.add(
            Consent(
                id=uuid7(),
                user_id=user.id,
                purpose=decision.purpose,
                granted=decision.granted,
                version=CONSENT_DOCUMENT_VERSION,
                granted_at=now if decision.granted else None,
                revoked_at=None if decision.granted else now,
                ip_hash=ip_hash,
                user_agent=user_agent,
            )
        )

    await session.flush()
    # Re-read from the database rather than echoing the payload: the response is what
    # the mobile app renders its consent screen from, so it must reflect stored state.
    return await read_consents(user, session)
