"""Identity & relationship entities (ARCHITECTURE.md §4).

Columns marked 🔒 in the architecture document are stored as ``BYTEA`` here: they
hold an AES-256-GCM ciphertext produced by ``app.services.crypto``, not a value.
Consequence, accepted in §5.1: they are not sortable or filterable in SQL.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import CoachingMode, LinkStatus, UserRole
from app.models.base import Base, PkMixin, SoftDeleteMixin, TimestampMixin

__all__ = [
    "User",
    "CoachProfile",
    "ClientProfile",
    "CoachClientLink",
    "Invitation",
    "RefreshToken",
    "EncryptionKey",
]


class User(PkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "user_account"  # "user" is reserved in PostgreSQL

    # citext keeps e-mail uniqueness case-insensitive without a functional index.
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(String(16), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'fr'"))
    #: IANA timezone. "Today" is meaningless in UTC for a user: a client at 23:00
    #: would already see tomorrow's session (Tech Lead, 2026-09-22).
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'Europe/Paris'")
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Set when a deletion request enters its 7-day grace window (§5.3).
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    coach_profile: Mapped[CoachProfile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    client_profile: Mapped[ClientProfile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("role IN ('coach','client')", name="role_valid"),
    )


class CoachProfile(PkMixin, TimestampMixin, Base):
    __tablename__ = "coach_profile"

    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("user_account.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    bio: Mapped[str | None] = mapped_column(Text)
    specialties: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    #: Hides the whole nutrition feature end-to-end when false (TASKS.md 2.5).
    offers_nutrition: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    default_coaching_mode: Mapped[CoachingMode] = mapped_column(
        String(16), nullable=False, server_default=text("'distance'")
    )

    user: Mapped[User] = relationship(back_populates="coach_profile")


class ClientProfile(PkMixin, TimestampMixin, Base):
    __tablename__ = "client_profile"

    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("user_account.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    birth_date_enc: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒
    #: Kept in clear: needed for the under-16 refusal (§5.2) without decrypting
    #: every row, and a year alone is not a direct identifier.
    birth_year: Mapped[int | None] = mapped_column(Integer)
    sex: Mapped[str | None] = mapped_column(String(16))
    height_cm_enc: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒
    goal: Mapped[str | None] = mapped_column(Text)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    user: Mapped[User] = relationship(back_populates="client_profile")

    @property
    def birth_date(self) -> date | None:  # pragma: no cover - set by the crypto service
        return getattr(self, "_birth_date", None)


class CoachClientLink(PkMixin, TimestampMixin, Base):
    """THE authorisation object. Everything a coach may read hangs off an `active` row."""

    __tablename__ = "coach_client_link"

    coach_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[LinkStatus] = mapped_column(String(16), nullable=False, index=True)
    coaching_mode: Mapped[CoachingMode] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("coach_id <> client_id", name="no_self_link"),
        CheckConstraint(
            "status IN ('pending','active','paused','revoked')", name="status_valid"
        ),
        CheckConstraint("coaching_mode IN ('presentiel','distance')", name="mode_valid"),
        # "A client has at most ONE active link at a time" (§4). Enforced by a
        # partial unique index, not only in the service layer: two concurrent
        # invitation acceptances must not both succeed.
        Index(
            "uq_link_one_active_per_client",
            "client_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_link_coach_status", "coach_id", "status"),
    )


class Invitation(PkMixin, TimestampMixin, Base):
    __tablename__ = "invitation"

    coach_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    #: 8 readable characters, unambiguous alphabet (no O/0/I/1).
    code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, index=True)
    email_hint: Mapped[str | None] = mapped_column(Text)
    coaching_mode: Mapped[CoachingMode] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL")
    )

    __table_args__ = (
        CheckConstraint("coaching_mode IN ('presentiel','distance')", name="mode_valid"),
    )


class RefreshToken(PkMixin, TimestampMixin, Base):
    """Rotating, revocable refresh token (30 days).

    Only a SHA-256 digest is stored: a database dump must not let anyone
    impersonate a session. Rotation is tracked by ``replaced_by`` so that reuse
    of an already-rotated token can be detected as theft and kill the family.
    """

    __tablename__ = "refresh_token"

    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("refresh_token.id", ondelete="SET NULL")
    )
    user_agent_hash: Mapped[str | None] = mapped_column(String(64))


class EncryptionKey(PkMixin, TimestampMixin, Base):
    """One DEK per user, itself encrypted by the KEK (§5.1).

    Destroying this row destroys every 🔒 value of that user at once — that is
    the crypto-shredding behind the right to erasure.
    """

    __tablename__ = "encryption_key"

    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("user_account.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    #: DEK wrapped with the KEK (AES-256-GCM), nonce prefixed.
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    kek_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Set instead of deleting when we need to prove the shredding happened.
    destroyed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("user_id", name="uq_encryption_key_user_id"),)
