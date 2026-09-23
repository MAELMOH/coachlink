"""`/coach/*` — invitations and the multi-client dashboard.

Every route here is behind the consent gate *and* reserved to the coach role. The
client list is additionally filtered by RLS, so a bug in this module cannot expose
another coach's clients — see ARCHITECTURE.md §4 on the two barriers.
"""

from __future__ import annotations

import base64
import binascii
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.consent_gate import require_consent
from app.core.deps import ClockDep, CurrentCoach, SessionDep, SettingsDep
from app.core.errors import ApiError, ErrorCode
from app.domain.enums import LinkStatus
from app.domain.ids import uuid7_timestamp_ms
from app.schemas.links import (
    ClientsPage,
    ClientSummary,
    InvitationCreateRequest,
    InvitationPublic,
)
from app.services import links as link_service
from app.services.audit import AuditAction, audit_context, record_access

router = APIRouter(prefix="/coach", tags=["coach"], dependencies=[Depends(require_consent)])

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 25


def _encode_cursor(link_id: UUID) -> str:
    """Opaque cursor over a UUID v7.

    UUID v7 is time-ordered (``app/domain/ids.py``), so the primary key doubles as the
    sort key and the cursor needs nothing else. Base64 is not security — it just stops
    clients from parsing and constructing cursors by hand, which would freeze the
    pagination implementation into the API contract.
    """
    return base64.urlsafe_b64encode(str(link_id).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> UUID:
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        value = UUID(base64.urlsafe_b64decode(padded).decode())
        uuid7_timestamp_ms(value)  # rejects a non-v7 id, which could not be ordered
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "Malformed cursor.") from exc
    return value


@router.post(
    "/invitations",
    status_code=status.HTTP_201_CREATED,
    summary="Create an invitation code for a new client",
    response_model=InvitationPublic,
)
async def create_invitation(
    payload: InvitationCreateRequest,
    request: Request,
    coach: CurrentCoach,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> InvitationPublic:
    invitation = await link_service.create_invitation(
        session,
        coach,
        coaching_mode=payload.coaching_mode,
        email_hint=payload.email_hint,
        now=clock.now(),
        settings=settings,
    )
    await record_access(
        session,
        actor_id=coach.id,
        action=AuditAction.INVITATION_CREATED,
        resource_type="invitation",
        resource_id=invitation.id,
        subject_id=coach.id,
        **audit_context(request, settings),
    )
    return InvitationPublic.model_validate(invitation)


@router.get(
    "/invitations",
    summary="Invitations issued by this coach",
    response_model=list[InvitationPublic],
)
async def list_invitations(coach: CurrentCoach, session: SessionDep) -> list[InvitationPublic]:
    invitations = await link_service.list_invitations(session, coach)
    return [InvitationPublic.model_validate(item) for item in invitations]


@router.get(
    "/clients",
    summary="The coach's clients (multi-client dashboard)",
    response_model=ClientsPage,
)
async def list_clients(
    request: Request,
    coach: CurrentCoach,
    session: SessionDep,
    settings: SettingsDep,
    link_status: LinkStatus | None = Query(default=None, alias="status"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> ClientsPage:
    query = link_service.list_clients_query(
        coach, statuses=frozenset({link_status}) if link_status else None
    )

    if cursor:
        from app.models.identity import CoachClientLink

        query = query.where(CoachClientLink.id < _decode_cursor(cursor))

    # Fetch one extra row to know whether a next page exists without a second COUNT.
    rows = (await session.execute(query.limit(limit + 1))).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    items = [
        ClientSummary(
            link_id=link.id,
            client_id=client.id,
            first_name=client.first_name,
            last_name=client.last_name,
            status=LinkStatus(link.status),
            coaching_mode=link.coaching_mode,
            started_at=link.started_at,
        )
        for link, client in rows
    ]

    # §4 requires an audit row on coach access to client data. The names on this screen
    # are client data, so the dashboard is audited like any other read — identifiers
    # only, never the rows themselves.
    await record_access(
        session,
        actor_id=coach.id,
        action=AuditAction.CLIENT_LIST_VIEWED,
        resource_type="coach_client_link",
        subject_id=coach.id,
        **audit_context(request, settings),
    )

    return ClientsPage(
        items=items,
        next_cursor=_encode_cursor(rows[-1][0].id) if has_more and rows else None,
    )
