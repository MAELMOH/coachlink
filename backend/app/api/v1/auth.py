"""`/auth/*` — registration, login, refresh rotation, logout.

Exempt from the consent gate by design (see ``app/api/consent_gate.py``): requiring
consent to log in would make consent impossible to grant.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.core.deps import ClockDep, SessionDep, SettingsDep
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserPublic,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_pair(user, access: str, refresh: str, settings) -> TokenPair:
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_ttl_minutes * 60,
        user=UserPublic.model_validate(user),
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Create a coach or client account",
    response_model=TokenPair,
)
async def register(
    payload: RegisterRequest,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> TokenPair:
    now = clock.now()
    user = await auth_service.register_user(session, payload, now=now, settings=settings)
    access, refresh = await auth_service.issue_token_pair(session, user, now=now, settings=settings)
    return _token_pair(user, access, refresh, settings)


@router.post("/login", summary="Exchange credentials for a token pair", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> TokenPair:
    now = clock.now()
    user = await auth_service.authenticate(session, payload, now=now, settings=settings)
    access, refresh = await auth_service.issue_token_pair(session, user, now=now, settings=settings)
    return _token_pair(user, access, refresh, settings)


@router.post(
    "/refresh",
    summary="Rotate a refresh token for a new pair",
    response_model=TokenPair,
)
async def refresh(
    payload: RefreshRequest,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> TokenPair:
    now = clock.now()
    user, access, new_refresh = await auth_service.rotate_refresh_token(
        session, payload.refresh_token, now=now, settings=settings
    )
    return _token_pair(user, access, new_refresh, settings)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the presented refresh token (or every session)",
)
async def logout(payload: LogoutRequest, session: SessionDep, clock: ClockDep) -> Response:
    await auth_service.logout(
        session, payload.refresh_token, now=clock.now(), all_sessions=payload.all_sessions
    )
    # 204 whether or not the token existed: a different answer would turn logout into a
    # way to test whether a token is live.
    return Response(status_code=status.HTTP_204_NO_CONTENT)
