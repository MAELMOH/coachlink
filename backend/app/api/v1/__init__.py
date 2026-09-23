"""API v1 routers.

One module per domain. Each router is mounted here so ``create_app`` has a single
aggregation point and the OpenAPI document stays ordered.

Mount order is the order `front` reads the generated Dart client in, so it follows the
user's journey — auth, then self, then the coach side, then the relationship — rather
than the alphabet.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth, coach, links, me

# NOTE: `health` is deliberately NOT mounted here. Probes are mounted at the root by
# `create_app()` — an orchestrator's liveness check should not have to know about API
# versions, and a second copy under /api/v1 would be one more path to keep out of the
# consent gate for no benefit.
api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(coach.router)
api_router.include_router(links.router)

__all__ = ["api_router"]
