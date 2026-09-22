"""API v1 routers.

One module per domain. Each router is mounted here so ``create_app`` has a single
aggregation point and the OpenAPI document stays ordered.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter()
api_router.include_router(health.router)

__all__ = ["api_router"]
