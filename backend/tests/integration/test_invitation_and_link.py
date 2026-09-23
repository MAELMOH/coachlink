"""Invitation → link → coach dashboard, and the isolation that hangs off it.

``tests/rls/test_rls_isolation.py`` proves the database barrier in raw SQL. This module
proves the *API* barrier on the same scenario: coach A must not see coach B's client
through any endpoint, and a paused or revoked link must cut access immediately.

ARCHITECTURE.md §4 asks for the rule to be enforced twice and tested as a nominal case,
not an exotic one — so the cross-coach attempt here is an ordinary test, run every time.
"""

from __future__ import annotations

import pytest

from tests.integration.conftest import error_code

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"
MANDATORY_CONSENTS = ["tos", "privacy", "health_data"]


async def _register(db_client, role: str, **overrides):
    from app.domain.ids import uuid7

    payload = {
        "email": f"{role}-{uuid7().hex[:10]}@coachlink-qa.fr",
        "password": PASSWORD,
        "role": role,
        "first_name": role.capitalize(),
        "last_name": "Test",
        **overrides,
    }
    if role == "client":
        payload.setdefault("birth_date", "1990-05-04")

    response = await db_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _grant_consents(db_client, token: str) -> None:
    response = await db_client.post(
        "/api/v1/me/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"decisions": [{"purpose": p, "granted": True} for p in MANDATORY_CONSENTS]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["missing_mandatory"] == []


async def _consented(db_client, role: str):
    created = await _register(db_client, role)
    await _grant_consents(db_client, created["access_token"])
    return created


def _auth(created) -> dict[str, str]:
    return {"Authorization": f"Bearer {created['access_token']}"}


async def _link_coach_and_client(db_client, coach, client, mode: str = "distance"):
    invitation = await db_client.post(
        "/api/v1/coach/invitations",
        headers=_auth(coach),
        json={"coaching_mode": mode},
    )
    assert invitation.status_code == 201, invitation.text
    code = invitation.json()["code"]

    accepted = await db_client.post(f"/api/v1/invitations/{code}/accept", headers=_auth(client))
    assert accepted.status_code == 200, accepted.text
    return accepted.json()


class TestInvitationLifecycle:
    async def test_code_is_eight_unambiguous_characters(self, db_client) -> None:
        """§4: 8 readable characters. No O/0 or I/1 — codes get read aloud and retyped."""
        coach = await _consented(db_client, "coach")
        response = await db_client.post(
            "/api/v1/coach/invitations", headers=_auth(coach), json={"coaching_mode": "distance"}
        )
        code = response.json()["code"]

        assert len(code) == 8
        assert not set(code) & set("O0I1L"), f"ambiguous characters in {code!r}"

    async def test_accepting_creates_an_active_link_and_starts_the_trial(self, db_client) -> None:
        coach = await _consented(db_client, "coach")
        client = await _consented(db_client, "client")

        link = await _link_coach_and_client(db_client, coach, client)
        assert link["status"] == "active"
        assert link["coach_id"] == coach["user"]["id"]
        assert link["client_id"] == client["user"]["id"]
        assert link["started_at"] is not None

    async def test_a_code_cannot_be_used_twice(self, db_client) -> None:
        """Atomicity lives in `consume_invitation` (migration 9c3d1e7b45a2)."""
        coach = await _consented(db_client, "coach")
        first_client = await _consented(db_client, "client")
        second_client = await _consented(db_client, "client")

        invitation = await db_client.post(
            "/api/v1/coach/invitations", headers=_auth(coach), json={"coaching_mode": "distance"}
        )
        code = invitation.json()["code"]

        assert (
            await db_client.post(f"/api/v1/invitations/{code}/accept", headers=_auth(first_client))
        ).status_code == 200

        replay = await db_client.post(
            f"/api/v1/invitations/{code}/accept", headers=_auth(second_client)
        )
        assert error_code(replay) == "INVITATION_INVALID"

    async def test_unknown_and_used_codes_are_indistinguishable(self, db_client) -> None:
        """Otherwise the endpoint becomes a code oracle to brute-force."""
        client = await _consented(db_client, "client")
        response = await db_client.post(
            "/api/v1/invitations/ZZZZZZZZ/accept", headers=_auth(client)
        )
        assert error_code(response) == "INVITATION_INVALID"

    async def test_a_coach_cannot_accept_an_invitation(self, db_client) -> None:
        coach = await _consented(db_client, "coach")
        other_coach = await _consented(db_client, "coach")

        invitation = await db_client.post(
            "/api/v1/coach/invitations", headers=_auth(coach), json={"coaching_mode": "distance"}
        )
        response = await db_client.post(
            f"/api/v1/invitations/{invitation.json()['code']}/accept",
            headers=_auth(other_coach),
        )
        assert error_code(response) == "WRONG_ROLE"

    async def test_a_client_cannot_issue_invitations(self, db_client) -> None:
        client = await _consented(db_client, "client")
        response = await db_client.post(
            "/api/v1/coach/invitations", headers=_auth(client), json={"coaching_mode": "distance"}
        )
        assert error_code(response) == "WRONG_ROLE"

    async def test_a_client_cannot_have_two_active_coaches(self, db_client) -> None:
        """§4: at most one active link per client — enforced by a partial unique index."""
        client = await _consented(db_client, "client")
        await _link_coach_and_client(db_client, await _consented(db_client, "coach"), client)

        second_coach = await _consented(db_client, "coach")
        invitation = await db_client.post(
            "/api/v1/coach/invitations",
            headers=_auth(second_coach),
            json={"coaching_mode": "distance"},
        )
        response = await db_client.post(
            f"/api/v1/invitations/{invitation.json()['code']}/accept", headers=_auth(client)
        )
        assert response.status_code == 409, response.text


class TestCrossCoachIsolationThroughTheApi:
    """Risk #1, at the HTTP layer. The RLS suite covers the same scenario in raw SQL."""

    async def test_a_coach_only_sees_their_own_clients(self, db_client) -> None:
        coach_a = await _consented(db_client, "coach")
        coach_b = await _consented(db_client, "coach")
        client_a = await _consented(db_client, "client")
        client_b = await _consented(db_client, "client")

        await _link_coach_and_client(db_client, coach_a, client_a)
        await _link_coach_and_client(db_client, coach_b, client_b)

        page = await db_client.get("/api/v1/coach/clients", headers=_auth(coach_a))
        assert page.status_code == 200, page.text

        visible = {item["client_id"] for item in page.json()["items"]}
        assert client_a["user"]["id"] in visible
        assert client_b["user"]["id"] not in visible, (
            "LEAK: coach A's dashboard lists a client belonging to coach B"
        )

    async def test_a_coach_cannot_read_another_coachs_invitations(self, db_client) -> None:
        coach_a = await _consented(db_client, "coach")
        coach_b = await _consented(db_client, "coach")

        await db_client.post(
            "/api/v1/coach/invitations", headers=_auth(coach_a), json={"coaching_mode": "distance"}
        )
        listing = await db_client.get("/api/v1/coach/invitations", headers=_auth(coach_b))
        assert listing.json() == []

    async def test_a_coach_cannot_touch_another_coachs_link(self, db_client) -> None:
        coach_a = await _consented(db_client, "coach")
        coach_b = await _consented(db_client, "coach")
        client_a = await _consented(db_client, "client")

        link = await _link_coach_and_client(db_client, coach_a, client_a)

        response = await db_client.patch(
            f"/api/v1/links/{link['id']}", headers=_auth(coach_b), json={"status": "revoked"}
        )
        assert response.status_code == 404, (
            "coach B could address a link they are not part of; RLS should hide it entirely"
        )


class TestLinkStatusTransitions:
    async def test_client_can_pause_sharing_and_the_coach_loses_the_client(self, db_client) -> None:
        """§5.3 right to restriction. The promise on the "my data" screen must be real."""
        coach = await _consented(db_client, "coach")
        client = await _consented(db_client, "client")
        link = await _link_coach_and_client(db_client, coach, client)

        paused = await db_client.patch(
            f"/api/v1/links/{link['id']}", headers=_auth(client), json={"status": "paused"}
        )
        assert paused.status_code == 200, paused.text
        assert paused.json()["status"] == "paused"

        page = await db_client.get("/api/v1/coach/clients?status=active", headers=_auth(coach))
        assert page.json()["items"] == []

    async def test_a_paused_link_can_be_resumed(self, db_client) -> None:
        coach = await _consented(db_client, "coach")
        client = await _consented(db_client, "client")
        link = await _link_coach_and_client(db_client, coach, client)

        await db_client.patch(
            f"/api/v1/links/{link['id']}", headers=_auth(client), json={"status": "paused"}
        )
        resumed = await db_client.patch(
            f"/api/v1/links/{link['id']}", headers=_auth(client), json={"status": "active"}
        )
        assert resumed.json()["status"] == "active"

    async def test_a_revoked_link_is_final(self, db_client) -> None:
        """Reactivating a revocation must go through a fresh invitation the client
        accepts again — not a coach-side toggle."""
        coach = await _consented(db_client, "coach")
        client = await _consented(db_client, "client")
        link = await _link_coach_and_client(db_client, coach, client)

        revoked = await db_client.patch(
            f"/api/v1/links/{link['id']}", headers=_auth(coach), json={"status": "revoked"}
        )
        assert revoked.json()["status"] == "revoked"

        reactivate = await db_client.patch(
            f"/api/v1/links/{link['id']}", headers=_auth(coach), json={"status": "active"}
        )
        assert reactivate.status_code == 409
        assert error_code(reactivate) == "CONFLICT"

    async def test_revoking_frees_the_client_for_a_new_coach(self, db_client) -> None:
        client = await _consented(db_client, "client")
        first_coach = await _consented(db_client, "coach")
        link = await _link_coach_and_client(db_client, first_coach, client)

        await db_client.patch(
            f"/api/v1/links/{link['id']}", headers=_auth(client), json={"status": "revoked"}
        )

        second_coach = await _consented(db_client, "coach")
        new_link = await _link_coach_and_client(db_client, second_coach, client)
        assert new_link["status"] == "active"


class TestPagination:
    async def test_cursor_paginates_without_repeating_or_losing_rows(self, db_client) -> None:
        coach = await _consented(db_client, "coach")
        expected = set()
        for _ in range(3):
            client = await _consented(db_client, "client")
            await _link_coach_and_client(db_client, coach, client)
            expected.add(client["user"]["id"])

        seen: set[str] = set()
        cursor = None
        for _ in range(5):  # bounded: a cursor bug must fail the test, not hang it
            url = "/api/v1/coach/clients?limit=2"
            if cursor:
                url += f"&cursor={cursor}"
            page = (await db_client.get(url, headers=_auth(coach))).json()

            ids = [item["client_id"] for item in page["items"]]
            assert not (seen & set(ids)), "a row was returned on two different pages"
            seen.update(ids)

            cursor = page["next_cursor"]
            if not cursor:
                break

        assert seen == expected

    async def test_a_malformed_cursor_is_rejected(self, db_client) -> None:
        coach = await _consented(db_client, "coach")
        response = await db_client.get(
            "/api/v1/coach/clients?cursor=not-a-cursor", headers=_auth(coach)
        )
        assert error_code(response) == "VALIDATION_ERROR"
