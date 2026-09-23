"""Normalised error envelope (``app/core/errors.py``).

The error ``code`` is a published contract: the Flutter app branches on it and this suite
asserts on it. Renaming one silently breaks the mobile client, so these tests pin the
codes that other layers depend on, plus the envelope shape from ARCHITECTURE.md §8.
"""

from __future__ import annotations

import pytest

from app.core.errors import ApiError, ErrorCode, http_status_for


class TestEnvelopeShape:
    def test_payload_matches_the_documented_shape(self) -> None:
        error = ApiError(ErrorCode.CONSENT_REQUIRED, "Consentements requis")
        assert error.to_payload() == {
            "error": {
                "code": "CONSENT_REQUIRED",
                "message": "Consentements requis",
                "details": {},
            }
        }

    def test_details_are_carried_through(self) -> None:
        error = ApiError(
            ErrorCode.VALIDATION_ERROR,
            "Champ invalide",
            details={"field": "reps_done"},
        )
        assert error.to_payload()["error"]["details"] == {"field": "reps_done"}

    def test_is_raisable_and_keeps_its_message(self) -> None:
        with pytest.raises(ApiError) as caught:
            raise ApiError(ErrorCode.NOT_FOUND, "Programme introuvable")
        assert str(caught.value) == "Programme introuvable"
        assert caught.value.code == "NOT_FOUND"

    def test_details_default_is_not_shared_between_instances(self) -> None:
        """A mutable default would leak one request's details into another's response."""
        first = ApiError(ErrorCode.CONFLICT, "a")
        second = ApiError(ErrorCode.CONFLICT, "b")
        first.details["leaked"] = True
        assert second.details == {}


class TestStatusMapping:
    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            # RGPD: the blocking consent gate (ARCHITECTURE.md §5.2)
            (ErrorCode.CONSENT_REQUIRED, 403),
            (ErrorCode.PHOTO_NOT_SHARED, 403),
            # Isolation: risk #1 (§4 "Règle d'accès transversale")
            (ErrorCode.NO_ACTIVE_LINK, 403),
            (ErrorCode.LINK_PAUSED, 403),
            (ErrorCode.LINK_REVOKED, 403),
            (ErrorCode.WRONG_ROLE, 403),
            # Trial / read-only (§7)
            (ErrorCode.TRIAL_EXPIRED, 402),
            (ErrorCode.READ_ONLY_MODE, 403),
            # Offline replay (§8)
            (ErrorCode.IDEMPOTENCY_KEY_REQUIRED, 400),
            (ErrorCode.IDEMPOTENCY_KEY_REUSED, 409),
            # Auth
            (ErrorCode.INVALID_CREDENTIALS, 401),
            (ErrorCode.NOT_AUTHENTICATED, 401),
            (ErrorCode.RATE_LIMITED, 429),
        ],
    )
    def test_documented_status_codes(self, code: str, expected: int) -> None:
        assert http_status_for(code) == expected

    def test_unknown_code_falls_back_to_400(self) -> None:
        assert http_status_for("NOT_A_REAL_CODE") == 400

    def test_explicit_status_overrides_the_default(self) -> None:
        error = ApiError(ErrorCode.CONFLICT, "…", status_code=418)
        assert error.status_code == 418

    def test_status_is_derived_from_the_code_by_default(self) -> None:
        assert ApiError(ErrorCode.TRIAL_EXPIRED, "…").status_code == 402


class TestVocabularyIntegrity:
    """Guards against a code drifting out of sync with its HTTP status table."""

    @staticmethod
    def _declared_codes() -> dict[str, str]:
        return {
            name: value
            for name, value in vars(ErrorCode).items()
            if not name.startswith("_") and isinstance(value, str)
        }

    def test_every_code_has_an_explicit_http_status(self) -> None:
        missing = [
            name
            for name, value in self._declared_codes().items()
            # 400 is the fallback, so an explicit 400 is indistinguishable from "absent".
            # IDEMPOTENCY_KEY_REQUIRED is genuinely 400 and is asserted above.
            if http_status_for(value, default=0) == 0
        ]
        assert not missing, f"ErrorCode entries with no HTTP status mapping: {sorted(missing)}"

    def test_constant_name_equals_its_value(self) -> None:
        """``FOO = "BAR"`` would make the wire contract unpredictable from the code."""
        mismatched = {
            name: value for name, value in self._declared_codes().items() if name != value
        }
        assert not mismatched, f"ErrorCode name/value mismatch: {mismatched}"

    def test_codes_are_unique(self) -> None:
        values = list(self._declared_codes().values())
        assert len(values) == len(set(values))

    def test_isolation_and_consent_codes_are_distinguishable(self) -> None:
        """A client must be able to tell *why* it was refused.

        Collapsing "no link", "link paused" and "missing consent" into a single
        ``FORBIDDEN`` would leave the app unable to route the user to the right screen
        (re-consent vs. contact your coach vs. resubscribe).
        """
        distinct = {
            ErrorCode.FORBIDDEN,
            ErrorCode.NO_ACTIVE_LINK,
            ErrorCode.LINK_PAUSED,
            ErrorCode.LINK_REVOKED,
            ErrorCode.CONSENT_REQUIRED,
            ErrorCode.READ_ONLY_MODE,
        }
        assert len(distinct) == 6
