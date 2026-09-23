"""`/invitations/{code}/accept` and `PATCH /links/{id}`.

These two routes are what create and end the authorisation relationship, so they are
the most security-sensitive endpoints outside `/auth`. Both are behind the consent
gate: joining a coach means letting them process health data, which needs a legal
basis *before* the link exists, not after.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request

from app.api.consent_gate import require_consent
from app.core.deps import ClockDep, CurrentClient, CurrentUser, SessionDep, SettingsDep
from app.schemas.links import LinkPublic, LinkUpdateRequest
from app.services import links as link_service
from app.services.audit import AuditAction, audit_context, record_access

router = APIRouter(tags=["links"], dependencies=[Depends(require_consent)])


@router.post(
    "/invitations/{code}/accept",
    summary="Redeem an invitation code and create the coach link",
    response_model=LinkPublic,
)
async def accept_invitation(
    request: Request,
    client: CurrentClient,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
    code: str = Path(min_length=4, max_length=16),
) -> LinkPublic:
    link = await link_service.accept_invitation(
        session, client, code, now=clock.now(), settings=settings
    )
    await record_access(
        session,
        actor_id=client.id,
        action=AuditAction.INVITATION_ACCEPTED,
        resource_type="coach_client_link",
        resource_id=link.id,
        subject_id=client.id,
        **audit_context(request, settings),
    )
    return LinkPublic.model_validate(link)


@router.patch(
    "/links/{link_id}",
    summary="Pause, resume or revoke a coaching link",
    response_model=LinkPublic,
)
async def update_link(
    payload: LinkUpdateRequest,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
    link_id: UUID = Path(),
) -> LinkPublic:
    """Either party may change the status.

    The client pausing is the GDPR right-to-restriction switch of §5.3 — and because
    the RLS policies key off ``status = 'active'``, pausing cuts the coach off **at the
    database level**, not merely in this service. That is what makes the promise on the
    "my data" screen true rather than aspirational.
    """
    link = await link_service.update_link_status(
        session, user, link_id, payload.status, now=clock.now()
    )
    await record_access(
        session,
        actor_id=user.id,
        action=AuditAction.LINK_STATUS_CHANGED,
        resource_type="coach_client_link",
        resource_id=link.id,
        subject_id=link.client_id,
        **audit_context(request, settings),
    )
    return LinkPublic.model_validate(link)
