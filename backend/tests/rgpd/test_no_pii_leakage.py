"""No personal data in logs, and none in push payloads (ARCHITECTURE.md §2.3, §5.4).

Two leaks that bypass every other control in the system:

**Logs.** Encrypting ``weight_kg`` in the database is undone the moment a request body is
logged in clear. Logs also travel further than the database — Sentry, log aggregation,
support screenshots — and §2.3 states logs carry *no PII*, with pseudonymised identifiers
and a 30-day retention.

**Push payloads.** FCM and APNs are operated outside the EU and are unavoidable for mobile
push (§5.4). The mitigation the architecture commits to is that the payload is opaque —
``{"n": "<uuid>"}`` — with the real content fetched afterwards over the authenticated API.
A notification reading "Marie: see you Monday 6pm" ships a name and a message body to a
non-EU processor, contradicting the privacy policy. The payload shape is therefore a
compliance control, not a formatting preference.
"""

from __future__ import annotations

import json
import re

import pytest

from app.domain.ids import uuid7
from tests.support.pending import require_any

pytestmark = pytest.mark.rgpd

#: Values planted in test input; none may resurface in a log line or a push payload.
PII_SAMPLES = {
    "email": "marie.dupont@example.com",
    "first_name": "Marie",
    "last_name": "Dupont",
    "password": "hunter2-correct-horse",
    "weight": "72.5",
    "message_body": "Rendez-vous lundi 18h",
    "birth_date": "1994-03-17",
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature",
}

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def _assert_clean(blob: str, context: str) -> None:
    found = [name for name, value in PII_SAMPLES.items() if value in blob]
    assert not found, f"{context} leaked {sorted(found)}: {blob[:400]}"
    assert not EMAIL_RE.search(blob), f"{context} contains an email address: {blob[:400]}"


class TestPushPayload:
    """§5.4: data-only, opaque, `{"n": "<uuid>"}`."""

    @pytest.fixture
    def build_payload(self):
        return require_any(
            [
                ("app.services.push", "build_push_payload"),
                ("app.services.notifications", "build_push_payload"),
                ("app.domain.notifications", "build_push_payload"),
            ]
        )

    def test_payload_is_the_opaque_envelope(self, build_payload) -> None:
        notification_id = uuid7()
        payload = build_payload(
            notification_id=notification_id,
            notification_type="message_received",
            recipient_name=PII_SAMPLES["first_name"],
            preview=PII_SAMPLES["message_body"],
        )
        assert set(payload) == {"n"}, (
            f"push payload carries keys beyond the opaque reference: {sorted(payload)}. "
            "§5.4 specifies exactly {'n': '<uuid>'} because FCM/APNs sit outside the EU."
        )
        assert payload["n"] == str(notification_id)

    def test_payload_contains_no_pii_whatsoever(self, build_payload) -> None:
        payload = build_payload(
            notification_id=uuid7(),
            notification_type="message_received",
            recipient_name=PII_SAMPLES["first_name"],
            preview=PII_SAMPLES["message_body"],
        )
        _assert_clean(json.dumps(payload, default=str), "push payload")

    def test_payload_has_no_title_or_body_keys(self, build_payload) -> None:
        """A ``notification`` block makes the OS render text — and makes it visible to
        the push provider. Data-only keeps delivery silent and opaque."""
        payload = build_payload(notification_id=uuid7(), notification_type="session_reminder")
        forbidden = {"notification", "title", "body", "subtitle", "alert", "message"}
        assert not forbidden & set(payload), (
            f"payload contains display keys {sorted(forbidden & set(payload))}; the "
            "notification would be rendered by the OS from provider-visible content"
        )

    def test_notification_type_is_not_in_the_payload(self, build_payload) -> None:
        """Even the type is metadata.

        ``{"n": id, "type": "trial_ending"}`` tells the provider this user's trial is
        expiring. Small, but it is exactly the kind of inference §5.4 rules out, and the
        app can read the type from the API along with the content.
        """
        payload = build_payload(notification_id=uuid7(), notification_type="trial_ending")
        assert "trial_ending" not in json.dumps(payload, default=str)

    def test_payload_is_stable_and_small(self, build_payload) -> None:
        payload = build_payload(notification_id=uuid7(), notification_type="program_published")
        assert len(json.dumps(payload)) < 200


class TestNotificationRowPayload:
    """``notification.payload`` is JSONB and documented "sans PII" (§4)."""

    def test_stored_payload_carries_no_personal_data(self) -> None:
        build = require_any(
            [
                ("app.services.push", "build_notification_payload"),
                ("app.services.notifications", "build_notification_payload"),
            ]
        )
        payload = build(
            notification_type="message_received",
            sender_name=PII_SAMPLES["first_name"],
            preview=PII_SAMPLES["message_body"],
        )
        _assert_clean(json.dumps(payload, default=str), "notification.payload")


class TestStructlogRedaction:
    """§2.3: structured logs, pseudonymised ids, never a body on a sensitive route."""

    @pytest.fixture
    def redact(self):
        return require_any(
            [
                ("app.core.logging", "redact_processor"),
                ("app.core.logging", "redact"),
                ("app.core.log", "redact_processor"),
            ]
        )

    def test_known_sensitive_keys_are_redacted(self, redact) -> None:
        event = {
            "event": "user.login",
            "email": PII_SAMPLES["email"],
            "password": PII_SAMPLES["password"],
            "first_name": PII_SAMPLES["first_name"],
            "authorization": f"Bearer {PII_SAMPLES['token']}",
        }
        result = redact(None, "info", dict(event))
        _assert_clean(json.dumps(result, default=str), "log event")

    def test_nested_structures_are_redacted(self, redact) -> None:
        """PII rarely arrives at the top level — it is inside the request body."""
        event = {
            "event": "measurement.created",
            "payload": {
                "client": {"email": PII_SAMPLES["email"], "weight_kg": PII_SAMPLES["weight"]},
                "notes": [PII_SAMPLES["message_body"]],
            },
        }
        result = redact(None, "info", event)
        _assert_clean(json.dumps(result, default=str), "nested log event")

    def test_user_ids_survive_redaction(self, redact) -> None:
        """Redaction must stay debuggable.

        Stripping identifiers too would make incident response impossible, which pushes
        engineers to log PII "just this once". A pseudonymous id is the compromise §2.3
        asks for.
        """
        user_id = str(uuid7())
        result = redact(None, "info", {"event": "x", "user_id": user_id, "request_id": "abc"})
        rendered = json.dumps(result, default=str)
        assert "abc" in rendered, "request_id was stripped; logs become untraceable"
        assert user_id in rendered or "user_id" in result


class TestSensitiveRouteBodies:
    """No request body on routes carrying health data (§5.4)."""

    def test_sensitive_routes_are_declared(self) -> None:
        sensitive = require_any(
            [
                ("app.core.logging", "NO_BODY_LOG_ROUTES"),
                ("app.core.logging", "SENSITIVE_ROUTES"),
            ]
        )
        paths = {str(p) for p in sensitive}
        expected_fragments = ("measurement", "progress-photo", "message", "nutrition", "auth")
        missing = [f for f in expected_fragments if not any(f in p for p in paths)]
        assert not missing, (
            f"routes handling health data or credentials are not excluded from body "
            f"logging: {missing}"
        )
