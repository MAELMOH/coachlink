"""GDPR compliance tables + billing (ARCHITECTURE.md §4, §5, §7)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import (
    BillingEventType,
    BillingProviderName,
    ConsentPurpose,
    DataRequestStatus,
    DataRequestType,
    PlanCode,
    SubjectType,
    SubscriptionStatus,
)
from app.models.base import Base, PkMixin, TimestampMixin

__all__ = [
    "ActiveClientSnapshot",
    "AuditLog",
    "BillingEvent",
    "Consent",
    "DataRequest",
    "IdempotencyRecord",
    "Subscription",
]


class Consent(PkMixin, TimestampMixin, Base):
    """Granular, versioned, journalled consent (§5.2).

    Rows are append-only: a revocation writes ``revoked_at`` and a new row is
    created on re-grant. The history is the proof of compliance, so nothing here
    is ever updated in place beyond ``revoked_at``.
    """

    __tablename__ = "consent"

    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[ConsentPurpose] = mapped_column(String(32), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Hashed, never the raw IP — an IP is personal data.
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "purpose IN ('tos','privacy','health_data','progress_photos','marketing')",
            name="purpose_valid",
        ),
        Index("ix_consent_user_purpose", "user_id", "purpose", "created_at"),
    )


class DataRequest(PkMixin, TimestampMixin, Base):
    """Export or erasure request (§5.3)."""

    __tablename__ = "data_request"

    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[DataRequestType] = mapped_column(String(16), nullable=False)
    status: Mapped[DataRequestStatus] = mapped_column(String(16), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Object key of the encrypted ZIP; purged after 24 h.
    export_key: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    #: End of the 7-day retraction window for a deletion.
    execute_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    error_code: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint("type IN ('export','deletion')", name="type_valid"),
        Index("ix_data_request_user_type", "user_id", "type", "status"),
    )


class AuditLog(PkMixin, Base):
    """Mandatory on every coach access to a client's sensitive data (§4).

    No ``updated_at``: an audit trail is append-only. Carries identifiers only —
    never the value that was read.
    """

    __tablename__ = "audit_log"

    actor_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    #: Whose data was touched — what makes cross-tenant access auditable.
    subject_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), index=True
    )
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (Index("ix_audit_log_subject_occurred", "subject_id", "occurred_at"),)


class Subscription(PkMixin, TimestampMixin, Base):
    __tablename__ = "subscription"

    subject_type: Mapped[SubjectType] = mapped_column(String(16), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    plan_code: Mapped[PlanCode] = mapped_column(String(32), nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(String(16), nullable=False, index=True)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider: Mapped[BillingProviderName] = mapped_column(
        String(16), nullable=False, server_default=text("'manual'")
    )
    provider_ref: Mapped[str | None] = mapped_column(Text)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("subject_type IN ('client','coach')", name="subject_type_valid"),
        CheckConstraint(
            "status IN ('trialing','active','past_due','canceled')", name="status_valid"
        ),
        CheckConstraint("provider IN ('manual','stripe')", name="provider_valid"),
        Index("ix_subscription_subject", "subject_type", "subject_id", "status"),
    )


class BillingEvent(PkMixin, TimestampMixin, Base):
    """Accounting trail.

    Kept **anonymised** for 10 years after an account deletion (§5.3): the
    accounting obligation outlives the person, so ``subscription_id`` is nulled
    rather than the row being deleted.
    """

    __tablename__ = "billing_event"

    subscription_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("subscription.id", ondelete="SET NULL"), index=True
    )
    type: Mapped[BillingEventType] = mapped_column(String(32), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'EUR'"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    #: Webhook idempotency (§7): the same provider event is processed once.
    provider_event_id: Mapped[str | None] = mapped_column(Text, unique=True)
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActiveClientSnapshot(PkMixin, TimestampMixin, Base):
    """Monthly materialisation of "active client" — the commission base (§7).

    The unique (coach, client, month) constraint is what makes the monthly Celery
    job idempotent and replayable.
    """

    __tablename__ = "active_client_snapshot"

    coach_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    #: First day of the civil month.
    period_month: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Which signal(s) made the client active — auditable, no PII.
    reasons: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (
        UniqueConstraint(
            "coach_id", "client_id", "period_month", name="uq_active_client_snapshot_period"
        ),
    )


class IdempotencyRecord(PkMixin, TimestampMixin, Base):
    """Replay cache for ``Idempotency-Key`` (§8).

    The mobile app replays its offline queue, so an identical replay must return
    the original response, and the *same key with a different payload* must be
    rejected (``IDEMPOTENCY_KEY_REUSED``) — hence the request fingerprint.
    """

    __tablename__ = "idempotency_record"

    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    __table_args__ = (UniqueConstraint("user_id", "endpoint", "key", name="uq_idempotency_scope"),)
