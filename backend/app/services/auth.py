"""Registration, login, refresh rotation and logout (ARCHITECTURE.md §2.2, §8).

Token model, and why it is split in two:

* the **access token** is a 15-minute JWT — stateless, so no database round-trip on
  every request;
* the **refresh token** is a 30-day opaque random string — *revocable*, which a JWT
  cannot be, and stored only as a SHA-256 digest so a database dump does not hand an
  attacker live sessions.

Refresh tokens rotate: using one issues a new one and marks the old as replaced. That
makes **theft detectable**. If a stolen token is replayed after the legitimate client
has already rotated it, we see a token that is both known and already-replaced — a
situation that cannot happen in normal use — and revoke the whole family. The user is
logged out of that lineage, which is the correct outcome: one of the two holders is an
attacker and we cannot tell which.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.engine import Row
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import apply_rls_context
from app.core.errors import ApiError, ErrorCode
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    verify_password,
)
from app.domain.age import is_old_enough
from app.domain.enums import UserRole
from app.domain.ids import uuid7
from app.models.identity import ClientProfile, CoachProfile, RefreshToken, User
from app.schemas.auth import LoginRequest, RegisterRequest

__all__ = [
    "authenticate",
    "issue_token_pair",
    "logout",
    "register_user",
    "rotate_refresh_token",
]

log = get_logger(__name__)


async def register_user(
    session: AsyncSession, payload: RegisterRequest, *, now: datetime, settings: Settings
) -> User:
    """Create a user plus the profile matching their role.

    The under-16 refusal happens **before** the row is written: a rejected signup must
    leave no trace of a minor's birth date in the database.
    """
    if payload.role is UserRole.CLIENT:
        if payload.birth_date is None:
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                "A birth date is required to open a client account.",
                details={"field": "birth_date"},
            )
        if not is_old_enough(payload.birth_date, now.date(), settings.minimum_age_years):
            raise ApiError(
                ErrorCode.UNDERAGE,
                f"Accounts are restricted to users aged {settings.minimum_age_years} or over.",
                details={"minimum_age_years": settings.minimum_age_years},
            )

    # The id is generated application-side (UUID v7, PG16 has no uuidv7()), which lets
    # us bind the RLS principal *before* the row exists. That is required, not merely
    # tidy: SQLAlchemy inserts with `RETURNING`, and PostgreSQL applies the SELECT
    # policy to a RETURNING clause. Under an anonymous context `user_account_select`
    # matches nothing, so the insert is rejected with "new row violates row-level
    # security policy" even though the INSERT policy itself is `WITH CHECK (true)`.
    user_id = uuid7()
    await apply_rls_context(session, user_id, str(payload.role))

    user = User(
        id=user_id,
        email=payload.email,
        password_hash=hash_password(payload.password, settings),
        role=payload.role,
        first_name=payload.first_name,
        last_name=payload.last_name,
        locale=payload.locale,
        timezone=payload.timezone,
    )
    session.add(user)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        # The unique index on a citext column is what makes this case-insensitive:
        # "Bob@x.fr" cannot become a second account for bob@x.fr.
        raise ApiError(
            ErrorCode.EMAIL_ALREADY_USED, "This e-mail address is already registered."
        ) from exc

    if payload.role is UserRole.COACH:
        session.add(CoachProfile(id=uuid7(), user_id=user.id))
    else:
        # Only the birth *year* is stored in clear, for the age check; the full date is
        # a 🔒 column filled by the crypto service (§5.1, section 2.7).
        session.add(
            ClientProfile(
                id=uuid7(),
                user_id=user.id,
                birth_year=payload.birth_date.year if payload.birth_date else None,
            )
        )

    await session.flush()
    log.info("auth.registered", role=str(payload.role))
    return user


async def authenticate(
    session: AsyncSession, payload: LoginRequest, *, now: datetime, settings: Settings
) -> User:
    """Verify credentials in constant-ish time and return the user.

    A missing account and a wrong password produce the **same** error code and both pay
    the cost of an Argon2 verification. Skipping the hash when the e-mail is unknown
    would turn login latency into an account-enumeration oracle.
    """
    # A plain `SELECT ... WHERE email = :email` returns nothing here: the request has no
    # principal yet, and `user_account_select` is fail-closed. Hence the narrow
    # SECURITY DEFINER lookup (migration 9c3d1e7b45a2), which returns credentials only.
    row = (
        await session.execute(
            text("SELECT id, password_hash, role, deleted_at FROM authenticate_lookup(:email)"),
            {"email": payload.email},
        )
    ).first()

    if row is None or row.deleted_at is not None:
        # Hash against a throwaway value so the timing matches the found-user path.
        verify_password(payload.password, _dummy_hash(settings), settings)
        raise ApiError(ErrorCode.INVALID_CREDENTIALS, "Invalid e-mail or password.")

    if not verify_password(payload.password, row.password_hash, settings):
        raise ApiError(ErrorCode.INVALID_CREDENTIALS, "Invalid e-mail or password.")

    # Credentials check out: bind the principal so the ORM load below (and every write
    # that follows in this transaction) runs under the right RLS identity.
    await apply_rls_context(session, row.id, str(row.role))

    user = await session.scalar(select(User).where(User.id == row.id))
    if user is None:  # pragma: no cover - the lookup just found it
        raise ApiError(ErrorCode.INVALID_CREDENTIALS, "Invalid e-mail or password.")

    # Parameters get bumped over time; upgrade the stored hash on a successful login,
    # which is the only moment the plaintext is legitimately available.
    if needs_rehash(user.password_hash, settings):
        user.password_hash = hash_password(payload.password, settings)

    user.last_login_at = now
    if payload.timezone:
        user.timezone = payload.timezone

    log.info("auth.login", actor=str(user.id)[:8])
    return user


_DUMMY_CACHE: dict[tuple[int, int, int], str] = {}


def _dummy_hash(settings: Settings) -> str:
    """A real Argon2 hash to verify against when the account does not exist.

    Computed once per parameter set: recomputing it on every failed login would itself
    be a timing signal, and it must use the *current* cost parameters, otherwise the
    unknown-account path is measurably cheaper than the wrong-password path and login
    becomes an account-enumeration oracle.
    """
    key = (settings.argon2_time_cost, settings.argon2_memory_cost_kib, settings.argon2_parallelism)
    cached = _DUMMY_CACHE.get(key)
    if cached is None:
        cached = hash_password("not-a-real-password", settings)
        _DUMMY_CACHE[key] = cached
    return cached


async def issue_token_pair(
    session: AsyncSession,
    user: User,
    *,
    now: datetime,
    settings: Settings,
    family_id: UUID | None = None,
) -> tuple[str, str]:
    """Mint an access/refresh pair. ``family_id`` continues an existing lineage."""
    access = create_access_token(user.id, str(user.role), now=now, settings=settings)

    raw_refresh = generate_refresh_token()
    session.add(
        RefreshToken(
            id=uuid7(),
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            family_id=family_id or uuid7(),
            expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    await session.flush()
    return access, raw_refresh


async def rotate_refresh_token(
    session: AsyncSession, raw_token: str, *, now: datetime, settings: Settings
) -> tuple[User, str, str]:
    """Exchange a refresh token for a new pair, detecting replay of a stolen one."""
    stored = await _resolve_refresh_token(session, raw_token)

    if stored is None:
        raise ApiError(ErrorCode.TOKEN_INVALID, "Unknown refresh token.")

    # The caller presented a refresh token and no access token, so the transaction is
    # still anonymous. Bind the owner now: everything below — the family revocation,
    # the new token row, the user load — is governed by `user_id = current_user`
    # policies and would otherwise silently affect zero rows.
    await apply_rls_context(session, stored.user_id, None)

    if stored.revoked_at is not None or stored.replaced_by is not None:
        # Already used or already revoked. In normal operation a client never replays a
        # rotated token, so this is theft until proven otherwise: burn the whole family.
        await _revoke_family(session, stored.family_id, now=now)
        # Commit BEFORE raising. The request is about to fail, and the session
        # dependency rolls back on any exception — which would quietly undo the
        # revocation and leave the stolen token usable. This is the one place where a
        # service commits on its own, because the security action must outlive the
        # failed request that triggered it.
        await session.commit()
        log.warning("auth.refresh_reuse_detected", family=str(stored.family_id)[:8])
        raise ApiError(
            ErrorCode.TOKEN_REVOKED,
            "This refresh token has already been used; all sessions in its family were "
            "revoked as a precaution.",
        )

    if stored.expires_at <= now:
        raise ApiError(ErrorCode.TOKEN_EXPIRED, "Refresh token has expired.")

    user = await session.scalar(select(User).where(User.id == stored.user_id))
    if user is None or user.deleted_at is not None:
        raise ApiError(ErrorCode.TOKEN_INVALID, "Account no longer exists.")

    await apply_rls_context(session, user.id, str(user.role))

    access, raw_refresh = await issue_token_pair(
        session, user, now=now, settings=settings, family_id=stored.family_id
    )

    replacement = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_refresh))
    )
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.id == stored.id)
        .values(revoked_at=now, replaced_by=replacement.id if replacement else None)
    )
    await session.flush()

    return user, access, raw_refresh


async def logout(
    session: AsyncSession, raw_token: str, *, now: datetime, all_sessions: bool = False
) -> None:
    """Revoke the presented token, or every session of its owner.

    Deliberately silent when the token is unknown: logout must never become a way to
    probe which tokens exist, and a client clearing a stale token is not an error.
    """
    stored = await _resolve_refresh_token(session, raw_token)
    if stored is None:
        return

    # Same reason as in `rotate_refresh_token`: logging out is done without an access
    # token, so the principal has to be bound before any policy-governed write.
    await apply_rls_context(session, stored.user_id, None)

    if all_sessions:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == stored.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
    else:
        await _revoke_family(session, stored.family_id, now=now)
    await session.flush()


async def _resolve_refresh_token(session: AsyncSession, raw_token: str) -> Row | None:
    """Look a refresh token up by digest, before any principal is bound.

    Goes through the SECURITY DEFINER function of migration ``9c3d1e7b45a2``: the
    ``refresh_token`` RLS policy is ``user_id = current_user``, and refresh/logout are
    by definition performed without an access token, so an ORM query here matches zero
    rows and every refresh fails with "unknown token".

    The *digest* is passed, never the token: the raw secret would otherwise appear in
    ``pg_stat_statements`` and in any statement log.
    """
    return (
        await session.execute(
            text(
                "SELECT id, user_id, family_id, expires_at, revoked_at, replaced_by "
                "FROM resolve_refresh_token(:token_hash)"
            ),
            {"token_hash": hash_refresh_token(raw_token)},
        )
    ).first()


async def _revoke_family(session: AsyncSession, family_id: UUID, *, now: datetime) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
