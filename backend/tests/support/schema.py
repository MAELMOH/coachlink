"""Build the test schema the way production builds it: with Alembic.

Why not ``Base.metadata.create_all``
------------------------------------
``create_all`` emits tables and indexes and **nothing else**. Everything that makes
CoachLink's schema actually safe lives outside the ORM metadata:

* the ``ENABLE``/``FORCE ROW LEVEL SECURITY`` statements and every ``CREATE POLICY``
  (``7a1c4e2b9d30``) — i.e. the *entire* second barrier against coach A reading
  coach B's client data, which ARCHITECTURE.md §4 calls the number-one risk;
* the ``citext`` conversion on ``user_account.email``;
* the ``set_updated_at`` trigger that ``GET /sync?since=`` depends on;
* the ``resolve_invitation`` SECURITY DEFINER function.

A suite built with ``create_all`` therefore runs against a schema with no policies at
all. The RLS tests then fail for the wrong reason, or — worse, once someone "fixes"
them by relaxing the assertions — pass while proving nothing.

Migrating instead has a second benefit: every test run is also a test of the migration
chain itself, so a migration that does not apply cleanly is caught here rather than on
a staging database.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config

from alembic import command
from tests.support.database import to_asyncpg

__all__ = ["BACKEND_ROOT", "alembic_config", "upgrade_to_head"]

#: backend/ — the directory holding alembic.ini and the alembic/ package.
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def alembic_config(owner_url: str) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    # Read by alembic/env.py::_database_url. Passed as an attribute rather than an
    # environment variable so a parallel xdist worker cannot see another's database.
    cfg.attributes["db_url"] = to_asyncpg(owner_url)
    return cfg


def upgrade_to_head(owner_url: str) -> None:
    """Apply the full migration chain as the schema owner."""
    command.upgrade(alembic_config(owner_url), "head")
