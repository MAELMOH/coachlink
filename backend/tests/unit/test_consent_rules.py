"""The consent rules, as pure functions (ARCHITECTURE.md §5.2).

Fast and DB-free on purpose: "which consents block the app" is a legal question with a
precise answer, and it should be provable without spinning up PostgreSQL. The gate's
HTTP behaviour is covered separately in ``tests/integration/test_consent_gate.py``.
"""

from __future__ import annotations

import pytest

from app.domain.consent import (
    has_all_mandatory_consents,
    is_mandatory,
    missing_mandatory_consents,
    normalise_purposes,
)
from app.domain.enums import ConsentPurpose

MANDATORY = ("tos", "privacy", "health_data")
OPTIONAL = ("progress_photos", "marketing")


class TestMandatorySet:
    def test_nothing_granted_blocks_on_all_three(self) -> None:
        assert missing_mandatory_consents([]) == {
            ConsentPurpose.TOS,
            ConsentPurpose.PRIVACY,
            ConsentPurpose.HEALTH_DATA,
        }

    @pytest.mark.parametrize("missing", MANDATORY)
    def test_any_single_missing_consent_still_blocks(self, missing: str) -> None:
        """The rule is *all three*, not "mostly consented"."""
        granted = [p for p in MANDATORY if p != missing]
        assert not has_all_mandatory_consents(granted)
        assert missing_mandatory_consents(granted) == {ConsentPurpose(missing)}

    def test_all_three_opens_the_gate(self) -> None:
        assert has_all_mandatory_consents(MANDATORY)
        assert missing_mandatory_consents(MANDATORY) == frozenset()


class TestOptionalConsents:
    @pytest.mark.parametrize("purpose", OPTIONAL)
    def test_optional_consents_are_not_mandatory(self, purpose: str) -> None:
        """`marketing` especially: gating the product on it would make the consent
        coerced, and coerced consent is not consent under the GDPR."""
        assert not is_mandatory(purpose)

    def test_optional_consents_alone_do_not_open_the_gate(self) -> None:
        assert not has_all_mandatory_consents(OPTIONAL)

    def test_declining_the_optional_ones_does_not_block(self) -> None:
        """The realistic default state: mandatory granted, optional declined."""
        assert has_all_mandatory_consents(MANDATORY)

    @pytest.mark.parametrize("purpose", MANDATORY)
    def test_mandatory_consents_report_as_mandatory(self, purpose: str) -> None:
        assert is_mandatory(purpose)


class TestRobustness:
    def test_enum_members_and_raw_strings_are_equivalent(self) -> None:
        """Consents arrive as strings from the database and as enums from Pydantic."""
        assert has_all_mandatory_consents([ConsentPurpose(p) for p in MANDATORY])
        assert has_all_mandatory_consents(list(MANDATORY))

    def test_unknown_purposes_are_dropped_not_trusted(self) -> None:
        """The vocabulary may grow over the years. An unknown value read back from an
        old row must never crash the gate — and must never satisfy it either."""
        assert normalise_purposes(["tos", "not_a_real_purpose"]) == {ConsentPurpose.TOS}
        assert not has_all_mandatory_consents(["tos", "privacy", "nonsense"])

    def test_unknown_purpose_is_not_mandatory(self) -> None:
        assert not is_mandatory("nonsense")

    def test_duplicates_do_not_change_the_verdict(self) -> None:
        assert has_all_mandatory_consents([*MANDATORY, *MANDATORY])
