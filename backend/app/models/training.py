"""Training entities: exercise, program, session, logged sets (ARCHITECTURE.md §4)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import (
    ExerciseSource,
    MediaLicense,
    ProgramStatus,
    WorkoutStatus,
)
from app.models.base import Base, PkMixin, SoftDeleteMixin, TimestampMixin

__all__ = [
    "Exercise",
    "PersonalRecord",
    "Program",
    "ProgramSession",
    "SessionExercise",
    "SetLog",
    "WorkoutLog",
]

#: Loads and reps are money-like quantities for the volume computation: Decimal,
#: never float. 0.5 kg increments are common, and float would drift.
LOAD_TYPE = Numeric(6, 2)


class Exercise(PkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Global catalogue (``owner_coach_id IS NULL``) or a coach's own exercise.

    ``media_license`` is mandatory on every media (§6): it is what makes the legal
    audit possible and it gates public visibility. Seeded rows come exclusively
    from yuhonas/free-exercise-db (Unlicense) with media re-hosted in our own EU
    bucket — hotlinking a third party is forbidden.
    """

    __tablename__ = "exercise"

    owner_coach_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    primary_muscles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    secondary_muscles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    equipment: Mapped[str | None] = mapped_column(String(64), index=True)
    mechanic: Mapped[str | None] = mapped_column(String(32))
    force: Mapped[str | None] = mapped_column(String(32))
    #: Object-storage keys in OUR bucket. Never an external URL.
    image_keys: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    video_key: Mapped[str | None] = mapped_column(Text)
    video_thumbnail_key: Mapped[str | None] = mapped_column(Text)
    media_license: Mapped[MediaLicense] = mapped_column(String(32), nullable=False)
    source: Mapped[ExerciseSource] = mapped_column(String(16), nullable=False)
    #: A coach video is private to its coach by default; publishing is explicit.
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    external_ref: Mapped[str | None] = mapped_column(Text, unique=True)

    __table_args__ = (
        CheckConstraint(
            "media_license IN ('public_domain','coach_owned')", name="media_license_valid"
        ),
        CheckConstraint("source IN ('seed','coach')", name="source_valid"),
        # A seeded (public-domain) exercise has no owner; a coach exercise has one.
        CheckConstraint(
            "(source = 'seed' AND owner_coach_id IS NULL)"
            " OR (source = 'coach' AND owner_coach_id IS NOT NULL)",
            name="source_matches_owner",
        ),
        Index("ix_exercise_primary_muscles", "primary_muscles", postgresql_using="gin"),
    )


class Program(PkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """``client_id IS NULL`` => reusable template owned by the coach."""

    __tablename__ = "program"

    coach_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[ProgramStatus] = mapped_column(String(16), nullable=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list[ProgramSession]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("status IN ('draft','published','archived')", name="status_valid"),
        CheckConstraint(
            "ends_on IS NULL OR starts_on IS NULL OR ends_on >= starts_on", name="dates_ordered"
        ),
        # A template is never published to anyone.
        CheckConstraint(
            "client_id IS NOT NULL OR status <> 'published'", name="template_not_published"
        ),
        Index("ix_program_coach_status", "coach_id", "status"),
    )


class ProgramSession(PkMixin, TimestampMixin, Base):
    """One training day inside a program.

    **Scheduling rule (single source of truth, Tech Lead 2026-09-22)**:
    ``day_index`` is relative to ``program.starts_on`` and is what normally
    applies — that is what keeps templates (``client_id IS NULL``) meaningful.
    ``scheduled_date`` is nullable and, when set, takes precedence.
    The civil day is resolved in the *user's* IANA timezone, never in UTC.
    """

    __tablename__ = "program_session"

    program_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("program.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_date: Mapped[date | None] = mapped_column(Date, index=True)
    order: Mapped[int] = mapped_column(
        "position", Integer, nullable=False, server_default=text("0")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    program: Mapped[Program] = relationship(back_populates="sessions")
    exercises: Mapped[list[SessionExercise]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("day_index >= 0", name="day_index_positive"),
        Index("ix_program_session_program_day", "program_id", "day_index"),
    )


class SessionExercise(PkMixin, TimestampMixin, Base):
    """The coach's prescription for one exercise inside one session."""

    __tablename__ = "session_exercise"

    program_session_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("program_session.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("exercise.id", ondelete="RESTRICT"), nullable=False
    )
    order: Mapped[int] = mapped_column(
        "position", Integer, nullable=False, server_default=text("0")
    )
    target_sets: Mapped[int] = mapped_column(Integer, nullable=False)
    target_reps: Mapped[int | None] = mapped_column(Integer)
    target_load_kg: Mapped[Decimal | None] = mapped_column(LOAD_TYPE)
    rest_seconds: Mapped[int | None] = mapped_column(Integer)
    tempo: Mapped[str | None] = mapped_column(String(16))
    coach_notes: Mapped[str | None] = mapped_column(Text)

    session: Mapped[ProgramSession] = relationship(back_populates="exercises")

    __table_args__ = (
        CheckConstraint("target_sets > 0", name="target_sets_positive"),
        CheckConstraint("target_reps IS NULL OR target_reps >= 0", name="target_reps_positive"),
        CheckConstraint(
            "target_load_kg IS NULL OR target_load_kg >= 0", name="target_load_positive"
        ),
        Index("ix_session_exercise_session", "program_session_id", "position"),
    )


class WorkoutLog(PkMixin, TimestampMixin, Base):
    """A session actually performed (or skipped) by a client."""

    __tablename__ = "workout_log"

    client_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    program_session_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("program_session.id", ondelete="SET NULL")
    )
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[WorkoutStatus] = mapped_column(String(16), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    client_notes: Mapped[str | None] = mapped_column(Text)
    rpe: Mapped[int | None] = mapped_column(Integer)
    #: Denormalised Σ(reps × load). Recomputed server-side on every set_log write
    #: by the pure function in app/domain/volume.py — the server is authoritative.
    total_volume_kg: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default=text("0")
    )
    #: Idempotency-Key of the request that created this row (§8). The mobile app
    #: replays its offline queue, so the same key must yield the same row.
    idempotency_key: Mapped[str | None] = mapped_column(String(128))

    sets: Mapped[list[SetLog]] = relationship(
        back_populates="workout_log", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('planned','in_progress','completed','skipped')", name="status_valid"
        ),
        CheckConstraint("rpe IS NULL OR (rpe BETWEEN 1 AND 10)", name="rpe_range"),
        CheckConstraint("total_volume_kg >= 0", name="volume_positive"),
        UniqueConstraint("client_id", "idempotency_key", name="uq_workout_log_idempotency"),
        Index("ix_workout_log_client_performed", "client_id", "performed_at"),
    )


class SetLog(PkMixin, TimestampMixin, Base):
    """One performed set.

    Conflict rule (§8): on `/sync`, **the client always wins** for set_log — they
    are the one who was at the gym.
    """

    __tablename__ = "set_log"

    workout_log_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workout_log.id", ondelete="CASCADE"), nullable=False
    )
    session_exercise_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("session_exercise.id", ondelete="SET NULL")
    )
    #: Kept alongside session_exercise_id so history survives program edits.
    exercise_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("exercise.id", ondelete="SET NULL")
    )
    set_index: Mapped[int] = mapped_column(Integer, nullable=False)
    reps_done: Mapped[int | None] = mapped_column(Integer)
    load_kg: Mapped[Decimal | None] = mapped_column(LOAD_TYPE)
    #: An uncompleted set contributes ZERO volume, whatever reps/load hold.
    is_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    rest_taken_seconds: Mapped[int | None] = mapped_column(Integer)

    workout_log: Mapped[WorkoutLog] = relationship(back_populates="sets")

    __table_args__ = (
        CheckConstraint("set_index >= 0", name="set_index_positive"),
        CheckConstraint("reps_done IS NULL OR reps_done >= 0", name="reps_positive"),
        CheckConstraint("load_kg IS NULL OR load_kg >= 0", name="load_positive"),
        UniqueConstraint(
            "workout_log_id", "session_exercise_id", "set_index", name="uq_set_log_position"
        ),
    )


class PersonalRecord(PkMixin, TimestampMixin, Base):
    __tablename__ = "personal_record"

    client_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("exercise.id", ondelete="CASCADE"), nullable=False
    )
    achieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    load_kg: Mapped[Decimal] = mapped_column(LOAD_TYPE, nullable=False)
    estimated_1rm: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    set_log_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("set_log.id", ondelete="SET NULL")
    )
    extra: Mapped[dict[str, object] | None] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_personal_record_client_exercise", "client_id", "exercise_id", "achieved_at"),
    )
