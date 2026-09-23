"""The client's 10-day free trial and the read-only switch (ARCHITECTURE.md §7).

    "``trial_ends_at = created_at + 10 jours`` à la création du lien coach-client. Après
    expiration sans abonnement → **mode lecture seule** (consultation du programme en
    cours et de l'historique, mais plus de log de séance ni de messagerie). **On ne coupe
    jamais l'accès à ses propres données — c'est aussi une exigence RGPD.**"

That last sentence is the one that matters most here. An expired trial is a *commercial*
state; it must never become a *data-access* restriction. Locking a client out of their own
weight history to pressure them into subscribing would breach the right of access
(Art. 15) — a billing bug that is simultaneously a compliance breach.

Spec-first: written before the module exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from tests.support.pending import require_any

TRIAL_DAYS = 10
LINK_CREATED_AT = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)

ACCESS_CANDIDATES = [
    ("app.domain.billing", "trial_access_level"),
    ("app.domain.subscription", "trial_access_level"),
    ("app.domain.trial", "trial_access_level"),
]
ENDS_AT_CANDIDATES = [
    ("app.domain.billing", "trial_ends_at"),
    ("app.domain.subscription", "trial_ends_at"),
    ("app.domain.trial", "trial_ends_at"),
]


@dataclass(frozen=True)
class SubscriptionView:
    trial_ends_at: datetime = LINK_CREATED_AT + timedelta(days=TRIAL_DAYS)
    status: str = "trialing"


def access_level(subscription: SubscriptionView, now: datetime) -> str:
    fn = require_any(ACCESS_CANDIDATES)
    return str(fn(subscription, now))


class TestTrialWindow:
    def test_trial_lasts_exactly_ten_days(self) -> None:
        fn = require_any(ENDS_AT_CANDIDATES)
        assert fn(LINK_CREATED_AT) == LINK_CREATED_AT + timedelta(days=10)

    def test_is_computed_from_the_given_instant_not_the_wall_clock(self) -> None:
        """Pure function: same input, same output, forever."""
        fn = require_any(ENDS_AT_CANDIDATES)
        assert fn(LINK_CREATED_AT) == fn(LINK_CREATED_AT)


class TestAccessTransitions:
    @pytest.mark.parametrize(
        "elapsed",
        [timedelta(0), timedelta(days=1), timedelta(days=9), timedelta(days=10, seconds=-1)],
    )
    def test_full_access_during_the_trial(self, elapsed: timedelta) -> None:
        level = access_level(SubscriptionView(), LINK_CREATED_AT + elapsed)
        assert level in ("full", "active"), f"expected full access, got {level!r}"

    @pytest.mark.parametrize(
        "elapsed",
        [timedelta(days=10), timedelta(days=10, seconds=1), timedelta(days=45)],
    )
    def test_read_only_after_expiry(self, elapsed: timedelta) -> None:
        level = access_level(SubscriptionView(), LINK_CREATED_AT + elapsed)
        assert level in ("read_only", "readonly"), f"expected read-only, got {level!r}"

    def test_boundary_is_not_off_by_one_day(self) -> None:
        """Day 10 exactly: the trial has ended.

        Written explicitly because an off-by-one here is invisible in manual testing and
        gives away (or wrongly denies) a day of paid product to every single client.
        """
        just_before = access_level(
            SubscriptionView(), LINK_CREATED_AT + timedelta(days=10) - timedelta(microseconds=1)
        )
        exactly_at = access_level(SubscriptionView(), LINK_CREATED_AT + timedelta(days=10))
        assert just_before != exactly_at

    def test_an_active_subscription_keeps_full_access_past_the_trial(self) -> None:
        subscribed = SubscriptionView(status="active")
        level = access_level(subscribed, LINK_CREATED_AT + timedelta(days=60))
        assert level in ("full", "active")

    def test_never_returns_a_no_access_level(self) -> None:
        """RGPD: expiry restricts *writes*, never access to one's own data.

        There must be no vocabulary for "locked out" in the trial state machine at all —
        if the value cannot be produced, the mistake cannot be made downstream.
        """
        for elapsed in (timedelta(days=0), timedelta(days=10), timedelta(days=365)):
            level = access_level(SubscriptionView(), LINK_CREATED_AT + elapsed)
            assert level not in ("none", "blocked", "locked", "denied"), (
                "an expired trial produced a no-access level; a client must always be "
                "able to consult their own data (ARCHITECTURE.md §7 + RGPD Art. 15)"
            )


class TestReadOnlyMeansWriteBlockedNotDataHidden:
    """Pins the *semantics* of read-only, which is where this rule usually goes wrong."""

    @pytest.mark.parametrize(
        "capability",
        ["view_current_program", "view_history", "view_measurements", "export_data"],
    )
    def test_read_capabilities_survive_expiry(self, capability: str) -> None:
        fn = require_any(
            [
                ("app.domain.billing", "is_capability_allowed"),
                ("app.domain.subscription", "is_capability_allowed"),
                ("app.domain.trial", "is_capability_allowed"),
            ]
        )
        expired = LINK_CREATED_AT + timedelta(days=30)
        assert fn(SubscriptionView(), expired, capability) is True, (
            f"{capability!r} was denied after trial expiry; reading one's own data is "
            "never a paid feature"
        )

    @pytest.mark.parametrize("capability", ["log_workout", "send_message"])
    def test_write_capabilities_are_blocked_after_expiry(self, capability: str) -> None:
        fn = require_any(
            [
                ("app.domain.billing", "is_capability_allowed"),
                ("app.domain.subscription", "is_capability_allowed"),
                ("app.domain.trial", "is_capability_allowed"),
            ]
        )
        expired = LINK_CREATED_AT + timedelta(days=30)
        assert fn(SubscriptionView(), expired, capability) is False
