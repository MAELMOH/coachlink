"""`/auth/*` end to end, against a real PostgreSQL under the unprivileged app role.

These run through HTTP rather than calling the service directly, because several of the
guarantees only exist once the whole stack is involved: the RLS context is bound by a
dependency, the fail-closed policies make an anonymous lookup return nothing, and the
error envelope is produced by an exception handler. Testing the service in isolation
would prove none of that — and it was precisely the "the login query returns zero rows
because the caller has no principal yet" class of bug that motivated this file.
"""

from __future__ import annotations

import pytest

from tests.integration.conftest import error_code

pytestmark = pytest.mark.integration

STRONG_PASSWORD = "correct-horse-battery-staple"


def _register_payload(**overrides):
    from app.domain.ids import uuid7

    base = {
        "email": f"client-{uuid7().hex[:10]}@coachlink-qa.fr",
        "password": STRONG_PASSWORD,
        "role": "client",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "birth_date": "1990-12-10",
        "timezone": "Europe/Paris",
    }
    return {**base, **overrides}


async def register(db_client, **overrides):
    response = await db_client.post("/api/v1/auth/register", json=_register_payload(**overrides))
    return response


class TestRegistration:
    async def test_register_returns_a_usable_token_pair(self, db_client) -> None:
        response = await register(db_client)
        assert response.status_code == 201, response.text

        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 15 * 60, "access token TTL must be 15 min per §2.2"
        assert body["access_token"] and body["refresh_token"]
        assert body["refresh_token"] != body["access_token"]

        # The access token works immediately: no e-mail verification step at MVP.
        me = await db_client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {body['access_token']}"}
        )
        assert me.status_code == 200
        assert me.json()["email"] == body["user"]["email"]

    async def test_password_is_never_echoed_back(self, db_client) -> None:
        """A hash in an API response is still a credential leak."""
        response = await register(db_client)
        assert "password" not in response.text.lower()

    async def test_duplicate_email_is_rejected_case_insensitively(self, db_client) -> None:
        """The citext column is what makes this true — see migration 42f9f7f51afa.

        Without it "Bob@x.fr" and "bob@x.fr" become two accounts and password recovery
        becomes ambiguous.
        """
        email = _register_payload()["email"]
        first = await register(db_client, email=email)
        assert first.status_code == 201

        second = await register(db_client, email=email.upper())
        assert second.status_code == 409
        assert error_code(second) == "EMAIL_ALREADY_USED"

    async def test_under_16_signup_is_refused(self, db_client) -> None:
        """§5.2: minors are refused at MVP to avoid parental-consent handling."""
        from datetime import date

        recent = date.today().replace(year=date.today().year - 15)
        response = await register(db_client, birth_date=recent.isoformat())
        assert error_code(response) == "UNDERAGE", response.text

    async def test_exactly_16_is_accepted(self, db_client) -> None:
        """Boundary: the rule is "under 16 refused", not "under 17"."""
        from datetime import date, timedelta

        today = date.today()
        sixteenth_birthday_today = today.replace(year=today.year - 16)
        response = await register(db_client, birth_date=sixteenth_birthday_today.isoformat())
        assert response.status_code == 201, response.text

        # ... and one day short of 16 is not.
        response = await register(
            db_client, birth_date=(sixteenth_birthday_today + timedelta(days=1)).isoformat()
        )
        assert error_code(response) == "UNDERAGE"

    async def test_coach_registration_needs_no_birth_date(self, db_client) -> None:
        """Data minimisation: we only collect the age we actually gate on."""
        response = await register(db_client, role="coach", birth_date=None)
        assert response.status_code == 201, response.text
        assert response.json()["user"]["role"] == "coach"

    async def test_weak_password_is_rejected_before_any_write(self, db_client) -> None:
        response = await register(db_client, password="short")
        assert response.status_code == 422


class TestLogin:
    async def test_login_with_correct_credentials(self, db_client) -> None:
        created = (await register(db_client)).json()
        response = await db_client.post(
            "/api/v1/auth/login",
            json={"email": created["user"]["email"], "password": STRONG_PASSWORD},
        )
        assert response.status_code == 200, response.text
        assert response.json()["user"]["id"] == created["user"]["id"]

    async def test_login_is_case_insensitive_on_email(self, db_client) -> None:
        created = (await register(db_client)).json()
        response = await db_client.post(
            "/api/v1/auth/login",
            json={"email": created["user"]["email"].upper(), "password": STRONG_PASSWORD},
        )
        assert response.status_code == 200, response.text

    async def test_wrong_password_and_unknown_account_are_indistinguishable(
        self, db_client
    ) -> None:
        """Same code, same status — otherwise login is an account-enumeration oracle."""
        created = (await register(db_client)).json()

        wrong_password = await db_client.post(
            "/api/v1/auth/login",
            json={"email": created["user"]["email"], "password": "not-the-right-one"},
        )
        unknown_account = await db_client.post(
            "/api/v1/auth/login",
            json={"email": "nobody-at-all@coachlink-qa.fr", "password": STRONG_PASSWORD},
        )

        assert wrong_password.status_code == unknown_account.status_code == 401
        assert error_code(wrong_password) == error_code(unknown_account) == "INVALID_CREDENTIALS"
        assert wrong_password.json() == unknown_account.json()

    async def test_login_updates_the_timezone(self, db_client) -> None:
        """Users travel; "today's session" is computed in their timezone (§4)."""
        created = (await register(db_client)).json()
        response = await db_client.post(
            "/api/v1/auth/login",
            json={
                "email": created["user"]["email"],
                "password": STRONG_PASSWORD,
                "timezone": "America/Montreal",
            },
        )
        assert response.json()["user"]["timezone"] == "America/Montreal"


class TestRefreshRotation:
    async def test_refresh_returns_a_new_pair_and_retires_the_old_token(self, db_client) -> None:
        created = (await register(db_client)).json()

        rotated = await db_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": created["refresh_token"]}
        )
        assert rotated.status_code == 200, rotated.text
        assert rotated.json()["refresh_token"] != created["refresh_token"]

    async def test_replaying_a_rotated_token_revokes_the_whole_family(self, db_client) -> None:
        """Theft detection.

        A legitimate client never replays a token it has already exchanged. Seeing one
        means two parties hold it and we cannot tell which is the attacker, so the safe
        move is to invalidate the lineage and force a fresh login.
        """
        created = (await register(db_client)).json()
        first = await db_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": created["refresh_token"]}
        )
        assert first.status_code == 200

        replay = await db_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": created["refresh_token"]}
        )
        assert error_code(replay) == "TOKEN_REVOKED", replay.text

        # The token legitimately obtained by the real client is burnt too: we cannot
        # tell the victim from the thief, so neither keeps the session.
        after = await db_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": first.json()["refresh_token"]}
        )
        assert after.status_code == 401

    async def test_unknown_refresh_token_is_rejected(self, db_client) -> None:
        response = await db_client.post("/api/v1/auth/refresh", json={"refresh_token": "x" * 64})
        assert error_code(response) == "TOKEN_INVALID"


class TestLogout:
    async def test_logout_revokes_the_refresh_token(self, db_client) -> None:
        created = (await register(db_client)).json()

        logout = await db_client.post(
            "/api/v1/auth/logout", json={"refresh_token": created["refresh_token"]}
        )
        assert logout.status_code == 204

        reuse = await db_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": created["refresh_token"]}
        )
        assert reuse.status_code == 401

    async def test_logout_of_an_unknown_token_still_answers_204(self, db_client) -> None:
        """Otherwise logout tells an attacker which tokens are live."""
        response = await db_client.post("/api/v1/auth/logout", json={"refresh_token": "y" * 64})
        assert response.status_code == 204


class TestAuthenticationGuards:
    async def test_me_requires_a_token(self, db_client) -> None:
        response = await db_client.get("/api/v1/me")
        assert error_code(response) == "NOT_AUTHENTICATED"

    async def test_garbage_token_is_rejected(self, db_client) -> None:
        response = await db_client.get("/api/v1/me", headers={"Authorization": "Bearer not.a.jwt"})
        assert error_code(response) == "TOKEN_INVALID"

    async def test_a_refresh_token_is_not_accepted_as_an_access_token(self, db_client) -> None:
        """The two have different lifetimes and revocation semantics; mixing them up
        would give a 30-day bearer credential to every endpoint."""
        created = (await register(db_client)).json()
        response = await db_client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {created['refresh_token']}"},
        )
        assert response.status_code == 401
