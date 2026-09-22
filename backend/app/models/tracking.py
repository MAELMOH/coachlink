"""Body tracking and nutrition — the most sensitive tables of the product.

Every value that ARCHITECTURE.md marks 🔒 is stored as ``BYTEA`` holding an
AES-256-GCM ciphertext (nonce ‖ ciphertext ‖ tag) with
``AAD = f"{table}:{row_id}:{column}"``. The AAD is what stops a ciphertext from
being moved from one row to another: decryption of a relocated value fails loudly
instead of returning someone else's weight.
"""

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
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import MealSlot, MeasurementSource, PhotoAngle, ProgramStatus
from app.models.base import Base, PkMixin, TimestampMixin

__all__ = [
    "BodyMeasurement",
    "ProgressPhoto",
    "NutritionPlan",
    "Meal",
    "NutritionLog",
]


class BodyMeasurement(PkMixin, TimestampMixin, Base):
    __tablename__ = "body_measurement"

    client_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # 🔒 — not sortable/filterable in SQL. Time series are decrypted and
    # aggregated service-side (§5.1): a few hundred points per client.
    weight_kg_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    body_fat_pct_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    waist_cm_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    hip_cm_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    chest_cm_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    arm_cm_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    thigh_cm_enc: Mapped[bytes | None] = mapped_column(LargeBinary)

    source: Mapped[MeasurementSource] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        CheckConstraint("source IN ('client','coach')", name="source_valid"),
        Index("ix_body_measurement_client_at", "client_id", "measured_at"),
    )


class ProgressPhoto(PkMixin, TimestampMixin, Base):
    """Body photo — encrypted server-side *before* the object upload (§5.1).

    ``shared_with_coach`` defaults to **false** at the database level, not merely
    in a Pydantic schema: a photo must never become visible to the coach because
    of a forgotten field somewhere up the stack.
    """

    __tablename__ = "progress_photo"

    client_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    angle: Mapped[PhotoAngle] = mapped_column(String(16), nullable=False)
    shared_with_coach: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    #: The `progress_photos` consent in force when the photo was stored.
    consent_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("consent.id", ondelete="SET NULL")
    )
    content_type: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint("angle IN ('front','side','back')", name="angle_valid"),
        Index("ix_progress_photo_client_at", "client_id", "taken_at"),
    )


class NutritionPlan(PkMixin, TimestampMixin, Base):
    __tablename__ = "nutrition_plan"

    coach_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    kcal_target_enc: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒
    protein_g_enc: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒
    carbs_g_enc: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒
    fat_g_enc: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒

    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[ProgramStatus] = mapped_column(String(16), nullable=False)

    meals: Mapped[list[Meal]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("status IN ('draft','published','archived')", name="status_valid"),
        Index("ix_nutrition_plan_client", "client_id", "status"),
    )


class Meal(PkMixin, TimestampMixin, Base):
    __tablename__ = "meal"

    nutrition_plan_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("nutrition_plan.id", ondelete="CASCADE"), nullable=False
    )
    slot: Mapped[MealSlot] = mapped_column(String(16), nullable=False)
    order: Mapped[int] = mapped_column("position", Integer, nullable=False, server_default=text("0"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    kcal_enc: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒
    #: JSONB in the architecture doc, but it is 🔒, so the serialised JSON is
    #: encrypted as a whole and stored as bytes.
    macros_enc: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒

    plan: Mapped[NutritionPlan] = relationship(back_populates="meals")

    __table_args__ = (
        CheckConstraint(
            "slot IN ('breakfast','lunch','dinner','snack')", name="slot_valid"
        ),
    )


class NutritionLog(PkMixin, TimestampMixin, Base):
    __tablename__ = "nutrition_log"

    client_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    meal_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("meal.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    followed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    comment_enc: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒

    __table_args__ = (
        UniqueConstraint("client_id", "meal_id", "date", name="uq_nutrition_log_day"),
        Index("ix_nutrition_log_client_date", "client_id", "date"),
    )
