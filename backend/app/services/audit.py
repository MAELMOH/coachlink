"""Audit trail (ARCHITECTURE.md §4).

    « ``audit_log`` → **obligatoire** sur tout accès coach aux données sensibles
    d'un client. »

Two rules make this table trustworthy rather than decorative:

* **identifiers only, never values.** An audit row says *that* coach X read client Y's
  measurements, never what they read. A log that copies the data it protects doubles the
  blast radius of a breach and is itself a health-data store.
* **append-only, and unreadable by the application.** The RLS policy on ``audit_log``
  grants INSERT and nothing else (migration ``7a1c4e2b9d30``), so a coach cannot check
  — or tamper with — what was recorded about them.
"""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy import func, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ids import uuid7
from app.models.compliance import AuditLog

__all__ = ["AuditAction", "hash_ip", "record_access"]


class AuditAction:
    """Closed vocabulary — grep-able, and safe to put in a dashboard."""

    CLIENT_LIST_VIEWED = "client_list.viewed"
    CLIENT_DATA_VIEWED = "client_data.viewed"
    LINK_STATUS_CHANGED = "link.status_changed"
    INVITATION_CREATED = "invitation.created"
    INVITATION_ACCEPTED = "invitation.accepted"


def hash_ip(ip: str | None, *, salt: str) -> str | None:
    """Pseudonymise an IP address. A raw IP is personal data (§5.4).

    Salted with the application secret: an unsalted hash of an IPv4 address is trivially
    reversible — there are only 2^32 of them, so a full rainbow table fits on a laptop.
    """
    if not ip:
        return None
    return hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()


async def record_access(
    session: AsyncSession,
    *,
    actor_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: UUID | None = None,
    subject_id: UUID | None = None,
    ip_hash: str | None = None,
    request_id: str | None = None,
) -> None:
    """Append one audit row.

    ``subject_id`` is *whose* data was touched — that is what makes a cross-tenant
    access reviewable afterwards, so it is filled even when it equals ``actor_id``.

    Written with a Core ``INSERT``, not ``session.add()``, and with the primary key
    supplied explicitly. The ORM's unit of work emits ``INSERT ... RETURNING`` to read
    back server-generated columns, and PostgreSQL evaluates the **SELECT** policy on a
    RETURNING clause. ``audit_log`` deliberately has no SELECT policy — the application
    must never read its own audit trail — so the ORM path fails with "new row violates
    row-level security policy" on a table it is in fact allowed to insert into. A plain
    INSERT with no RETURNING is both the fix and the honest description of what an
    append-only log needs.
    """
    await session.execute(
        insert(AuditLog).values(
            id=uuid7(),
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            subject_id=subject_id,
            occurred_at=func.now(),
            ip_hash=ip_hash,
            request_id=request_id,
        )
    )


def audit_context(request: Any, settings: Any) -> dict[str, str | None]:
    """Extract the non-identifying request metadata worth auditing."""
    client = getattr(request, "client", None)
    return {
        "ip_hash": hash_ip(
            getattr(client, "host", None), salt=settings.jwt_secret.get_secret_value()
        ),
        "request_id": getattr(request.state, "request_id", None),
    }
