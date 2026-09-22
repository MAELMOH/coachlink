"""Messaging, notifications, devices (ARCHITECTURE.md §4).

Messaging exists only when ``coach_client_link.coaching_mode = 'distance'``;
``presentiel`` disables it end-to-end, REST and WebSocket alike.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import DevicePlatform, NotificationType
from app.models.base import Base, PkMixin, TimestampMixin

__all__ = ["Conversation", "Message", "Notification", "DeviceToken"]


class Conversation(PkMixin, TimestampMixin, Base):
    __tablename__ = "conversation"

    coach_client_link_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("coach_client_link.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(PkMixin, TimestampMixin, Base):
    __tablename__ = "message"

    conversation_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    #: 🔒 The message body is encrypted at rest with the *client's* DEK, so that
    #: deleting the client's account crypto-shreds the whole conversation.
    body_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    attachment_key: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_message_conversation_sent", "conversation_id", "sent_at"),)


class Notification(PkMixin, TimestampMixin, Base):
    """In-app notification.

    ``payload`` carries NO PII (§5.4). The push actually sent through FCM/APNs is
    data-only and opaque — ``{"n": "<uuid>"}`` — and the app fetches the real
    content from the authenticated API. FCM/APNs are outside the EU; that
    minimisation is the mitigation.
    """

    __tablename__ = "notification"

    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[NotificationType] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_notification_user_scheduled", "user_id", "scheduled_for"),)


class DeviceToken(PkMixin, TimestampMixin, Base):
    __tablename__ = "device_token"

    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[DevicePlatform] = mapped_column(String(16), nullable=False)
    token: Mapped[str] = mapped_column(Text, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("platform IN ('ios','android')", name="platform_valid"),
        UniqueConstraint("token", name="uq_device_token_token"),
    )
