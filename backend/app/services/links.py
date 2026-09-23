"""Invitations and the coach↔client link (ARCHITECTURE.md §4, TASKS.md 2.2).

``coach_client_link`` is *the* authorisation object of this application: every single
thing a coach may read about a client hangs off an ``active`` row here. Two invariants
are therefore enforced by the database rather than by this module alone:

* a client has at most **one** ``active`` link (partial unique index, migration 1);
* an invitation code is consumed **atomically** (``consume_invitation``, migration 3),
  so two clients racing on the same code cannot both get a link.

Both are defended here too, for a clear error message — but the database is what makes
them true under concurrency.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import Select, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.core.logging import get_logger
from app.core.security import generate_invitation_code
from app.domain.enums import CoachingMode, LinkStatus, UserRole
from app.domain.ids import uuid7
from app.models.identity import ClientProfile, CoachClientLink, Invitation, User

__all__ = [
    "accept_invitation",
    "create_invitation",
    "list_clients_query",
    "list_invitations",
    "update_link_status",
]

log = get_logger(__name__)

#: Retries on the (astronomically unlikely) event of a code collision. 31^8 ≈ 8.5e11
#: possibilities, but a unique index exists precisely so we never rely on luck.
_CODE_ATTEMPTS = 5


async def create_invitation(
    session: AsyncSession,
    coach: User,
    *,
    coaching_mode: CoachingMode,
    email_hint: str | None,
    now: datetime,
    settings: Settings,
) -> Invitation:
    expires_at = now + timedelta(hours=settings.invitation_ttl_hours)

    for attempt in range(_CODE_ATTEMPTS):
        invitation = Invitation(
            id=uuid7(),
            coach_id=coach.id,
            code=generate_invitation_code(),
            email_hint=email_hint,
            coaching_mode=coaching_mode,
            expires_at=expires_at,
        )
        session.add(invitation)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            if attempt == _CODE_ATTEMPTS - 1:
                raise
            continue
        log.info("invitation.created", actor=str(coach.id)[:8], mode=str(coaching_mode))
        return invitation

    raise ApiError(ErrorCode.CONFLICT, "Could not allocate an invitation code.")


async def list_invitations(session: AsyncSession, coach: User) -> list[Invitation]:
    result = await session.scalars(
        select(Invitation)
        .where(Invitation.coach_id == coach.id)
        .order_by(Invitation.created_at.desc())
    )
    return list(result)


async def accept_invitation(
    session: AsyncSession, client: User, code: str, *, now: datetime, settings: Settings
) -> CoachClientLink:
    """Redeem a code and create the link.

    The consume-then-create order matters. Consuming first means a failure to create
    the link leaves a burnt code, which is recoverable (the coach reissues one). The
    reverse order would let a race create two links from one invitation, and a duplicate
    link is exactly the cross-client leak this application exists to prevent.
    """
    # `!=`, never `is not`. The column is a plain String(16), so SQLAlchemy hands back
    # the raw `'client'` string rather than the enum member; identity comparison is
    # False for every row ever loaded from the database and would reject every client.
    if client.role != UserRole.CLIENT:
        raise ApiError(ErrorCode.WRONG_ROLE, "Only a client account can accept an invitation.")

    existing = await session.scalar(
        select(func.count())
        .select_from(CoachClientLink)
        .where(
            CoachClientLink.client_id == client.id,
            CoachClientLink.status == LinkStatus.ACTIVE,
        )
    )
    if existing:
        raise ApiError(
            ErrorCode.CONFLICT,
            "This account already has an active coach. Leave the current one first.",
        )

    # Atomic: marks the invitation consumed and hands back its data in one statement,
    # or returns nothing if it was expired or already used (see migration 9c3d1e7b45a2).
    row = (
        await session.execute(
            text("SELECT id, coach_id, coaching_mode FROM consume_invitation(:code, :client)"),
            {"code": code.strip().upper(), "client": client.id},
        )
    ).first()

    if row is None:
        # Deliberately one code for all three cases (unknown / expired / consumed):
        # distinguishing them would let anyone probe which codes exist.
        raise ApiError(
            ErrorCode.INVITATION_INVALID,
            "This invitation code is invalid, expired or already used.",
        )

    if row.coach_id == client.id:  # pragma: no cover - blocked by a CHECK constraint too
        raise ApiError(ErrorCode.VALIDATION_ERROR, "You cannot coach yourself.")

    link = CoachClientLink(
        id=uuid7(),
        coach_id=row.coach_id,
        client_id=client.id,
        status=LinkStatus.ACTIVE,
        coaching_mode=CoachingMode(row.coaching_mode),
        started_at=now,
    )
    session.add(link)

    # The 10-day free trial starts when the relationship starts, not at signup (§7):
    # a client who registers and waits a week should still get their ten days.
    profile = await session.scalar(select(ClientProfile).where(ClientProfile.user_id == client.id))
    if profile is not None and profile.trial_ends_at is None:
        profile.trial_ends_at = now + timedelta(days=settings.client_trial_days)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(ErrorCode.CONFLICT, "This account already has an active coach.") from exc

    log.info("invitation.accepted", actor=str(client.id)[:8], mode=str(link.coaching_mode))
    return link


def list_clients_query(coach: User, *, statuses: frozenset[LinkStatus] | None = None) -> Select:
    """Links of ``coach`` joined to the client account, newest first.

    Returned as a query rather than rows so the router can paginate it. RLS applies on
    top of the explicit ``coach_id`` filter — the filter is for correctness and the
    index, the policy is the barrier that survives a forgotten filter.
    """
    query = (
        select(CoachClientLink, User)
        .join(User, User.id == CoachClientLink.client_id)
        .where(CoachClientLink.coach_id == coach.id)
        .order_by(CoachClientLink.created_at.desc())
    )
    if statuses:
        query = query.where(CoachClientLink.status.in_(statuses))
    return query


#: Transitions the API accepts. Reactivating a revoked link is deliberately absent:
#: a revocation is the client cutting the coach off, and undoing it must go through a
#: fresh invitation that the client accepts again — not a coach-side toggle.
_ALLOWED_TRANSITIONS: dict[LinkStatus, frozenset[LinkStatus]] = {
    LinkStatus.PENDING: frozenset({LinkStatus.ACTIVE, LinkStatus.REVOKED}),
    LinkStatus.ACTIVE: frozenset({LinkStatus.PAUSED, LinkStatus.REVOKED}),
    LinkStatus.PAUSED: frozenset({LinkStatus.ACTIVE, LinkStatus.REVOKED}),
    LinkStatus.REVOKED: frozenset(),
}


async def update_link_status(
    session: AsyncSession,
    actor: User,
    link_id: UUID,
    new_status: LinkStatus,
    *,
    now: datetime,
) -> CoachClientLink:
    link = await session.scalar(select(CoachClientLink).where(CoachClientLink.id == link_id))
    # RLS already hides links the actor is not part of, so "not found" here covers both
    # a wrong id and someone else's link — and says the same thing in both cases.
    if link is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Link not found.")

    if actor.id not in (link.coach_id, link.client_id):  # pragma: no cover - RLS filters first
        raise ApiError(ErrorCode.FORBIDDEN, "You are not part of this link.")

    current = LinkStatus(link.status)
    if new_status is current:
        return link

    if new_status not in _ALLOWED_TRANSITIONS[current]:
        raise ApiError(
            ErrorCode.CONFLICT,
            f"Cannot move a link from {current} to {new_status}.",
            details={"from": str(current), "to": str(new_status)},
        )

    link.status = new_status
    if new_status is LinkStatus.ACTIVE:
        link.ended_at = None
        if link.started_at is None:
            link.started_at = now
    elif new_status is LinkStatus.REVOKED:
        link.ended_at = now

    await session.flush()
    log.info("link.status_changed", actor=str(actor.id)[:8], to=str(new_status))
    return link
