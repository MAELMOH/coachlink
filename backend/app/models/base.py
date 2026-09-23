"""Declarative base and shared column mixins.

Importing this module must have **no side effect**: no connection, no mandatory
config read. ``Base.metadata`` has to be usable on its own by Alembic and by the
test suite.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, MetaData, func, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.ids import uuid7

__all__ = ["Base", "PkMixin", "SoftDeleteMixin", "TimestampMixin", "utcnow_column"]

# Explicit naming convention: Alembic autogenerate produces stable, reviewable
# constraint names instead of database-assigned ones.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        # Deliberately prints only the id: a default repr would spill decrypted
        # attributes into tracebacks and logs.
        pk = getattr(self, "id", None)
        return f"<{type(self).__name__} id={pk}>"


def utcnow_column(**kwargs: Any) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), **kwargs)


class PkMixin:
    """UUID v7 primary key, generated application-side (PG16 has no uuidv7()).

    ``gen_random_uuid()`` stays as a server-side safety net for rows inserted by
    raw SQL (seeds, migrations, psql), at the cost of losing time ordering for
    those — acceptable, they are not paginated by cursor.
    """

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    #: Drives `GET /sync?since=` — the delta is per record, not per column
    #: (Tech Lead, 2026-09-22). A DB-level trigger also maintains it, so a raw
    #: SQL update cannot make a row invisible to sync.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )


class SoftDeleteMixin:
    """Logical deletion. NOT used for the right to erasure, which is physical (§5.3)."""

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
