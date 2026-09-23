"""Behavioural proof of the second barrier: coach A cannot reach coach B's client.

``test_rls_configuration.py`` asserts the policies are switched on and forced. This module
asserts they actually *do* something — in raw SQL, as the unprivileged ``coachlink_app``
role, with **no FastAPI in the picture at all**.

That separation is the whole point. If these tests went through the API they would pass as
soon as the service layer filtered correctly, and would keep passing if the RLS policy were
deleted tomorrow. ARCHITECTURE.md §4 asks for two independent barriers; testing them
together would give us one barrier and a false sense of two.

Seeding runs through the schema-owner engine and deliberately bypasses the service layer,
so the rows exist regardless of what the API would have allowed.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.rls, pytest.mark.integration]


async def _table_exists(conn, name: str) -> bool:
    import sqlalchemy

    result = await conn.execute(
        sqlalchemy.text("SELECT to_regclass(:name) IS NOT NULL"), {"name": name}
    )
    return bool(result.scalar_one())


async def _as_user(conn, user_id, role: str = "coach") -> None:
    """Establish the request context the policies read.

    Mirrors exactly what ``back``'s ``get_session`` dependency does per transaction
    (``app.core.db.apply_rls_context``): ``set_config(..., is_local => true)``, which is
    transaction-scoped, so this must be called inside an open transaction.

    ``set_config`` rather than ``SET LOCAL`` is not a stylistic choice. ``SET`` takes no
    bind parameters, and ``SET LOCAL app.current_role = '...'`` is in fact a **syntax
    error** — ``current_role`` is a reserved SQL keyword, and PostgreSQL's grammar rejects
    it even behind the ``app.`` prefix. ``set_config()`` is an ordinary function call and
    is immune to both problems. Using the production helper's mechanism here also means
    this suite fails if that mechanism ever stops working.
    """
    import sqlalchemy

    from app.core.db import RLS_ROLE_SETTING, RLS_USER_SETTING

    await conn.execute(
        sqlalchemy.text("SELECT set_config(:k, :v, true)"),
        {"k": RLS_USER_SETTING, "v": str(user_id)},
    )
    await conn.execute(
        sqlalchemy.text("SELECT set_config(:k, :v, true)"),
        {"k": RLS_ROLE_SETTING, "v": role},
    )


@pytest.fixture
async def isolation_fixture(owner_engine, app_engine, schema_ready):
    """Two coaches, two clients, one active link each — the minimal leak scenario.

    Returns the seeded ids. Skips (rather than fails) while the schema has not landed, so
    the file is committed and ready the moment ``back`` ships the migration.
    """
    import sqlalchemy

    from app.domain.ids import uuid7
    from app.models.identity import User

    # Taken from the model rather than hardcoded: "user" is a reserved word in
    # PostgreSQL, so `back` named the table `user_account`. Reading __tablename__
    # here means a future rename shows up as a failing query, not as a silently
    # skipped file — this suite covers the project's number-one risk and must
    # never quietly disappear from the report.
    users_table = User.__tablename__

    required = (users_table, "coach_client_link", "body_measurement")
    async with owner_engine.connect() as conn:
        for table in required:
            if not await _table_exists(conn, table):
                pytest.skip(f"table {table!r} not migrated yet (waiting on `back`)")

    ids = {
        "coach_a": uuid7(),
        "coach_b": uuid7(),
        "client_a": uuid7(),
        "client_b": uuid7(),
        "link_a": uuid7(),
        "link_b": uuid7(),
        "measurement_a": uuid7(),
        "measurement_b": uuid7(),
    }

    async with owner_engine.begin() as conn:
        for key, role in (
            ("coach_a", "coach"),
            ("coach_b", "coach"),
            ("client_a", "client"),
            ("client_b", "client"),
        ):
            await conn.execute(
                sqlalchemy.text(
                    f"INSERT INTO {users_table} (id, email, password_hash, role, first_name, "
                    "last_name) VALUES (:id, :email, :pwd, :role, :fn, :ln)"
                ),
                {
                    "id": ids[key],
                    "email": f"{key}@rls.test",
                    "pwd": "x",
                    "role": role,
                    "fn": key,
                    "ln": "test",
                },
            )
        for link_key, coach_key, client_key in (
            ("link_a", "coach_a", "client_a"),
            ("link_b", "coach_b", "client_b"),
        ):
            await conn.execute(
                sqlalchemy.text(
                    "INSERT INTO coach_client_link (id, coach_id, client_id, status, "
                    "coaching_mode) VALUES (:id, :coach, :client, 'active', 'distance')"
                ),
                {"id": ids[link_key], "coach": ids[coach_key], "client": ids[client_key]},
            )
        for m_key, client_key in (("measurement_a", "client_a"), ("measurement_b", "client_b")):
            await conn.execute(
                sqlalchemy.text(
                    "INSERT INTO body_measurement (id, client_id, measured_at, source) "
                    "VALUES (:id, :client, now(), 'client')"
                ),
                {"id": ids[m_key], "client": ids[client_key]},
            )

    yield ids

    async with owner_engine.begin() as conn:
        await conn.execute(
            sqlalchemy.text("DELETE FROM body_measurement WHERE client_id = ANY(:ids)"),
            {"ids": [ids["client_a"], ids["client_b"]]},
        )
        await conn.execute(
            sqlalchemy.text("DELETE FROM coach_client_link WHERE id = ANY(:ids)"),
            {"ids": [ids["link_a"], ids["link_b"]]},
        )
        await conn.execute(
            sqlalchemy.text(f"DELETE FROM {users_table} WHERE id = ANY(:ids)"),
            {
                "ids": [
                    ids["coach_a"],
                    ids["coach_b"],
                    ids["client_a"],
                    ids["client_b"],
                ]
            },
        )


async def _measurements_visible_to(app_engine, user_id, role: str = "coach") -> set:
    import sqlalchemy

    async with app_engine.begin() as conn:
        await _as_user(conn, user_id, role)
        result = await conn.execute(sqlalchemy.text("SELECT id FROM body_measurement"))
        return {row[0] for row in result}


class TestCrossCoachRead:
    """Risk #1, tested as a nominal case."""

    async def test_coach_sees_only_their_own_clients_measurements(
        self, app_engine, isolation_fixture
    ) -> None:
        ids = isolation_fixture
        visible = await _measurements_visible_to(app_engine, ids["coach_a"])

        assert ids["measurement_a"] in visible, "coach A cannot see their own client's data"
        assert ids["measurement_b"] not in visible, (
            "RLS LEAK: coach A can read a measurement belonging to coach B's client, "
            "directly in SQL. This is the project's number-one risk realised."
        )

    async def test_the_leak_is_symmetric(self, app_engine, isolation_fixture) -> None:
        ids = isolation_fixture
        visible = await _measurements_visible_to(app_engine, ids["coach_b"])
        assert visible == {ids["measurement_b"]}

    async def test_client_sees_only_their_own_data(self, app_engine, isolation_fixture) -> None:
        ids = isolation_fixture
        visible = await _measurements_visible_to(app_engine, ids["client_a"], role="client")
        assert ids["measurement_a"] in visible
        assert ids["measurement_b"] not in visible

    async def test_unknown_user_sees_nothing(self, app_engine, isolation_fixture) -> None:
        from app.domain.ids import uuid7

        visible = await _measurements_visible_to(app_engine, uuid7())
        assert visible == set()


class TestCrossCoachWrite:
    """Reading is the headline risk; writing is the quieter one.

    A coach who can UPDATE or DELETE another coach's client data corrupts records without
    ever reading them. ``USING`` governs visibility, ``WITH CHECK`` governs writes — a
    policy that sets only the first leaves writes open.
    """

    async def test_coach_cannot_update_another_coachs_client_data(
        self, app_engine, isolation_fixture
    ) -> None:
        import sqlalchemy

        ids = isolation_fixture
        async with app_engine.begin() as conn:
            await _as_user(conn, ids["coach_a"])
            result = await conn.execute(
                sqlalchemy.text("UPDATE body_measurement SET source = 'coach' WHERE id = :id"),
                {"id": ids["measurement_b"]},
            )
            assert result.rowcount == 0, "coach A modified a row belonging to coach B's client"

    async def test_coach_cannot_delete_another_coachs_client_data(
        self, app_engine, isolation_fixture
    ) -> None:
        import sqlalchemy

        ids = isolation_fixture
        async with app_engine.begin() as conn:
            await _as_user(conn, ids["coach_a"])
            result = await conn.execute(
                sqlalchemy.text("DELETE FROM body_measurement WHERE id = :id"),
                {"id": ids["measurement_b"]},
            )
            assert result.rowcount == 0, "coach A deleted coach B's client's measurement"

    async def test_coach_cannot_insert_data_for_an_unlinked_client(
        self, app_engine, isolation_fixture
    ) -> None:
        """Needs ``WITH CHECK``. Without it a coach can plant rows on any client id."""
        import sqlalchemy

        from app.domain.ids import uuid7

        ids = isolation_fixture
        async with app_engine.begin() as conn:
            await _as_user(conn, ids["coach_a"])
            with pytest.raises(Exception):  # noqa: B017 - any refusal is a pass
                await conn.execute(
                    sqlalchemy.text(
                        "INSERT INTO body_measurement (id, client_id, measured_at, source) "
                        "VALUES (:id, :client, now(), 'coach')"
                    ),
                    {"id": uuid7(), "client": ids["client_b"]},
                )


class TestLinkStatusGatesAccess:
    """``active`` is the only status that grants access (ARCHITECTURE.md §4).

    ``paused`` is the RGPD "pause sharing with my coach" switch (§5.3) — if it does not
    actually cut database-level access, the app is telling users something untrue about
    their own data.
    """

    @pytest.mark.parametrize("status", ["paused", "revoked", "pending"])
    async def test_non_active_link_cuts_coach_access(
        self, app_engine, owner_engine, isolation_fixture, status: str
    ) -> None:
        import sqlalchemy

        ids = isolation_fixture
        async with owner_engine.begin() as conn:
            await conn.execute(
                sqlalchemy.text("UPDATE coach_client_link SET status = :s WHERE id = :id"),
                {"s": status, "id": ids["link_a"]},
            )

        visible = await _measurements_visible_to(app_engine, ids["coach_a"])
        assert ids["measurement_a"] not in visible, (
            f"link status {status!r} still grants the coach read access to client data; "
            "only 'active' may."
        )

    async def test_client_keeps_access_to_own_data_when_link_is_paused(
        self, app_engine, owner_engine, isolation_fixture
    ) -> None:
        """Pausing the coach relationship must not lock the client out of their own data.

        Same RGPD principle as the expired trial: sharing can stop, access to one's own
        record never does (Art. 15).
        """
        import sqlalchemy

        ids = isolation_fixture
        async with owner_engine.begin() as conn:
            await conn.execute(
                sqlalchemy.text("UPDATE coach_client_link SET status = 'paused' WHERE id = :id"),
                {"id": ids["link_a"]},
            )

        visible = await _measurements_visible_to(app_engine, ids["client_a"], role="client")
        assert ids["measurement_a"] in visible, (
            "pausing the coach link also cut the CLIENT off from their own measurements"
        )
