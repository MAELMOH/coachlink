"""FastAPI dependencies — the single, central place where a request acquires a
database session *and* its Row Level Security context.

Why centralised: if any service could open its own session, one forgotten
``SET LOCAL app.current_user_id`` would silently disable the second isolation
barrier and nothing would fail visibly. So :func:`get_session` is the only
request-scoped session factory, and it always sets the context.

Everything here is overridable through ``app.dependency_overrides``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.core.db import apply_rls_context, get_sessionmaker
from app.core.errors import ApiError, ErrorCode
from app.core.security import decode_token
from app.domain.enums import LinkStatus, UserRole
from app.models.identity import CoachClientLink, User

__all__ = [
    "ClockDep",
    "CurrentClient",
    "CurrentCoach",
    "CurrentUser",
    "SessionDep",
    "SettingsDep",
    "get_clock",
    "get_current_user",
    "get_session",
    "require_active_link",
    "require_client",
    "require_coach",
]

_system_clock = SystemClock()


def get_clock() -> Clock:
    """Injectable clock. Tests override this with ``FrozenClock``."""
    return _system_clock


SettingsDep = Annotated[Settings, Depends(get_settings)]
ClockDep = Annotated[Clock, Depends(get_clock)]


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Request-scoped transactional session with the RLS context applied.

    The principal is read from the JWT *before* the session opens, so the very
    first statement of the transaction already runs under the right identity.
    An anonymous request gets a NULL context, under which the policies match no
    row at all (fail-closed).
    """
    user_id: UUID | None = None
    role: str | None = None

    token = _bearer_token(request)
    if token:
        try:
            payload = decode_token(token)
            user_id, role = payload.user_id, payload.role
        except ApiError:
            # Let get_current_user produce the proper 401; the session simply
            # stays anonymous rather than trusting a token we could not verify.
            user_id, role = None, None

    request.state.user_id = user_id

    maker = get_sessionmaker()
    async with maker() as session:
        try:
            await apply_rls_context(session, user_id, role)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(request: Request, session: SessionDep) -> User:
    token = _bearer_token(request)
    if not token:
        raise ApiError(ErrorCode.NOT_AUTHENTICATED, "Authentication required.")

    payload = decode_token(token)  # raises TOKEN_EXPIRED / TOKEN_INVALID

    user = await session.scalar(select(User).where(User.id == payload.user_id))
    if user is None or user.deleted_at is not None:
        raise ApiError(ErrorCode.TOKEN_INVALID, "Account no longer exists.")

    request.state.user_id = user.id
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_coach(user: CurrentUser) -> User:
    if user.role != UserRole.COACH:
        raise ApiError(ErrorCode.WRONG_ROLE, "This endpoint is reserved for coaches.")
    return user


async def require_client(user: CurrentUser) -> User:
    if user.role != UserRole.CLIENT:
        raise ApiError(ErrorCode.WRONG_ROLE, "This endpoint is reserved for clients.")
    return user


CurrentCoach = Annotated[User, Depends(require_coach)]
CurrentClient = Annotated[User, Depends(require_client)]


async def require_active_link(
    session: AsyncSession,
    coach_id: UUID,
    client_id: UUID,
) -> CoachClientLink:
    """The first of the two barriers of ARCHITECTURE.md §4.

    A coach reaches a client's data **only** through an ``active`` link. PostgreSQL RLS
    enforces the same rule independently (migration ``7a1c4e2b9d30``); this one exists
    so the API answers a precise error code instead of an empty result set, and so the
    rule is visible in the code a reviewer reads.

    The distinct ``LINK_PAUSED`` / ``LINK_REVOKED`` codes are deliberate and safe: the
    coach already knows this relationship exists, so naming its state leaks nothing and
    lets the app say "your client paused sharing" instead of a blank screen.
    """
    link = await session.scalar(
        select(CoachClientLink).where(
            CoachClientLink.coach_id == coach_id,
            CoachClientLink.client_id == client_id,
        )
    )
    if link is None:
        raise ApiError(ErrorCode.NO_ACTIVE_LINK, "You are not linked to this client.", details={})

    status = LinkStatus(link.status)
    if status is LinkStatus.ACTIVE:
        return link
    if status is LinkStatus.PAUSED:
        raise ApiError(ErrorCode.LINK_PAUSED, "This client has paused sharing their data.")
    if status is LinkStatus.REVOKED:
        raise ApiError(ErrorCode.LINK_REVOKED, "This coaching relationship has ended.")
    raise ApiError(ErrorCode.NO_ACTIVE_LINK, "This invitation has not been accepted yet.")
