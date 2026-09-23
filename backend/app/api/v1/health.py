"""Liveness / readiness probes. Unauthenticated, rate-limit exempt, PII-free."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, Any]:
    settings = get_settings()
    return {"status": "ok", "environment": settings.environment, "version": "0.1.0"}


@router.get("/health/ready", summary="Readiness probe (checks PostgreSQL)")
async def readiness() -> dict[str, Any]:
    checks: dict[str, str] = {}
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {type(exc).__name__}"
    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks}
