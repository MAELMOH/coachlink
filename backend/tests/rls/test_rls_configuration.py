"""The second barrier: is Row Level Security actually switched on?

ARCHITECTURE.md §4 requires the coach↔client access rule to be enforced **twice** — once
in the FastAPI service layer and once by a PostgreSQL RLS policy. This module tests the
*configuration* of that second barrier; ``test_rls_isolation.py`` tests its *behaviour*.

Configuration is worth its own file because every failure mode here is silent:

* the app connects as a superuser  -> every policy is bypassed, no error, no log;
* ``ENABLE`` without ``FORCE``     -> the table owner bypasses the policy;
* a table gains columns of client data but nobody adds it to the policy list.

In all three cases the behavioural tests can still pass (the service layer catches the
access) while the second barrier is pure decoration. That is precisely the situation
defence-in-depth is supposed to prevent, so it gets asserted directly.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.rls, pytest.mark.integration]

#: Tables holding client-owned or link-scoped data (ARCHITECTURE.md §4).
#: A coach must only ever reach these rows through an ``active`` coach_client_link.
CLIENT_DATA_TABLES = frozenset(
    {
        "client_profile",
        "coach_client_link",
        "program",
        "program_session",
        "session_exercise",
        "workout_log",
        "set_log",
        "body_measurement",
        "progress_photo",
        "personal_record",
        "nutrition_plan",
        "meal",
        "nutrition_log",
        "conversation",
        "message",
    }
)


async def _fetch_all(engine, sql: str, **params):
    import sqlalchemy

    async with engine.connect() as conn:
        result = await conn.execute(sqlalchemy.text(sql), params)
        return result.mappings().all()


class TestApplicationRolePrivileges:
    """If the app role can bypass RLS, nothing else in this directory means anything."""

    async def test_app_role_is_not_superuser_and_cannot_bypass_rls(self, owner_engine) -> None:
        from tests.support.database import APP_ROLE

        rows = await _fetch_all(
            owner_engine,
            "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :role",
            role=APP_ROLE,
        )
        assert rows, f"role {APP_ROLE!r} does not exist — the API has no unprivileged identity"

        role = rows[0]
        assert role["rolsuper"] is False, (
            f"{APP_ROLE} is a SUPERUSER: PostgreSQL skips every RLS policy for it, so the "
            "entire second barrier against cross-coach data leakage is inactive"
        )
        assert role["rolbypassrls"] is False, (
            f"{APP_ROLE} has BYPASSRLS: policies are evaluated for nobody, the isolation "
            "tests below would pass while proving nothing"
        )

    async def test_the_suite_is_really_connected_as_the_unprivileged_role(self, app_engine) -> None:
        """Guards against a misconfigured ``TEST_DATABASE_URL_APP`` silently pointing at
        the owner — which would make every isolation assertion meaningless."""
        from tests.support.database import APP_ROLE

        rows = await _fetch_all(app_engine, "SELECT current_user AS who")
        assert rows[0]["who"] == APP_ROLE

    async def test_app_role_cannot_disable_rls(self, app_engine, schema_ready) -> None:
        """Only the table owner may ``ALTER TABLE ... DISABLE ROW LEVEL SECURITY``.

        An application-level SQL injection that reached DDL must not be able to take the
        barrier down.
        """
        import sqlalchemy

        with pytest.raises(Exception):  # noqa: B017 - any DB refusal is a pass
            async with app_engine.begin() as conn:
                await conn.execute(
                    sqlalchemy.text("ALTER TABLE body_measurement DISABLE ROW LEVEL SECURITY")
                )


class TestPolicyCoverage:
    async def test_every_client_data_table_has_rls_enabled(
        self, owner_engine, schema_ready
    ) -> None:
        rows = await _fetch_all(
            owner_engine,
            """
            SELECT c.relname AS table_name, c.relrowsecurity AS enabled
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
            """,
        )
        present = {r["table_name"]: r["enabled"] for r in rows}
        expected = CLIENT_DATA_TABLES & set(present)
        assert expected, "none of the client-data tables exist yet"

        unprotected = sorted(name for name in expected if not present[name])
        assert not unprotected, (
            f"client-data tables without RLS enabled: {unprotected}. A coach reaching "
            "these rows is stopped only by the service layer — one forgotten filter in a "
            "future endpoint leaks another coach's client data."
        )

    async def test_rls_is_forced_so_the_owner_cannot_bypass_it(
        self, owner_engine, schema_ready
    ) -> None:
        """``ENABLE`` alone exempts the table owner; ``FORCE`` closes that hole.

        ``back`` confirmed ``FORCE ROW LEVEL SECURITY`` is applied — this asserts it, since
        the difference is invisible until the day the app happens to connect as the owner.
        """
        rows = await _fetch_all(
            owner_engine,
            """
            SELECT c.relname AS table_name, c.relforcerowsecurity AS forced
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity
            """,
        )
        present = {r["table_name"]: r["forced"] for r in rows}
        relevant = CLIENT_DATA_TABLES & set(present)
        not_forced = sorted(name for name in relevant if not present[name])
        assert not not_forced, (
            f"RLS enabled but not FORCEd on: {not_forced}. The table owner — which is the "
            "role Alembic and any maintenance script use — silently bypasses the policy."
        )

    async def test_every_rls_table_actually_carries_a_policy(
        self, owner_engine, schema_ready
    ) -> None:
        """RLS enabled with zero policies denies everything — fail-closed, but it means a
        feature is quietly broken rather than protected. Both are bugs worth naming."""
        rows = await _fetch_all(
            owner_engine,
            """
            SELECT c.relname AS table_name, count(p.polname) AS policies
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_policy p ON p.polrelid = c.oid
            WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity
            GROUP BY c.relname
            """,
        )
        without = sorted(r["table_name"] for r in rows if r["policies"] == 0)
        assert not without, f"RLS enabled but no policy defined on: {without}"


class TestFailClosed:
    """No session context => no rows. The default must be denial, not exposure."""

    async def test_unset_context_exposes_nothing(self, app_engine, schema_ready) -> None:
        """``back`` states the policies read ``current_setting('app.current_user_id', true)``
        and that an unset value yields no rows. This is the single most important default
        in the schema: a code path that forgets to set the context must fail closed.
        """
        import sqlalchemy

        async with app_engine.connect() as conn:
            for table in sorted(CLIENT_DATA_TABLES):
                exists = await conn.execute(
                    sqlalchemy.text("SELECT to_regclass(:name) IS NOT NULL"), {"name": table}
                )
                if not exists.scalar_one():
                    continue
                result = await conn.execute(sqlalchemy.text(f"SELECT count(*) FROM {table}"))
                assert result.scalar_one() == 0, (
                    f"{table} returned rows with no app.current_user_id set. The policy "
                    "is not fail-closed: any endpoint that forgets to establish the "
                    "session context exposes every client's data to every caller."
                )
