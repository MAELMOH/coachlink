"""``is_client_active()`` — the basis of the coach's commission (ARCHITECTURE.md §7).

Spec as written: *"lien ``active`` **et** au moins une séance loguée **ou** une mesure
enregistrée **ou** un message échangé sur le mois civil"*.

This function decides what a coach is billed, so a wrong answer is a wrong invoice in
either direction. It is also flagged in ``TASKS.md`` Phase 0 as *"règle à figer avec le
chef de projet"* — still open. The tests below therefore split into two groups:

* **Settled** — behaviour that follows unambiguously from the sentence above.
* **Ambiguous** — cases the sentence does not decide. These are written but deliberately
  *not* asserted as pass/fail; they are recorded so the decision is made on purpose
  rather than by accident of implementation. Raised to ``tech-lead``.

Proposed contract (QA, open to change by ``back``)::

    is_client_active(link, month, activity) -> bool

with ``link`` exposing ``status`` / ``started_at`` / ``ended_at``, ``month`` a
``date`` inside the civil month, and ``activity`` exposing ``workout_logs`` /
``measurements`` / ``messages`` counted over that month.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest

from app.domain.enums import LinkStatus
from tests.support.pending import require_any

CANDIDATES = [
    ("app.domain.billing", "is_client_active"),
    ("app.domain.activity", "is_client_active"),
    ("app.domain.subscription", "is_client_active"),
]

SEPTEMBER = date(2026, 9, 1)


@dataclass(frozen=True)
class LinkView:
    status: LinkStatus = LinkStatus.ACTIVE
    started_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    ended_at: datetime | None = None


@dataclass(frozen=True)
class MonthActivity:
    workout_logs: int = 0
    measurements: int = 0
    messages: int = 0


def is_active(link: LinkView, activity: MonthActivity, month: date = SEPTEMBER) -> bool:
    fn = require_any(CANDIDATES)
    return fn(link, month, activity)


class TestSettledByTheSpec:
    """Cases the written rule decides on its own."""

    def test_active_link_with_a_logged_workout_is_billable(self) -> None:
        assert is_active(LinkView(), MonthActivity(workout_logs=1)) is True

    def test_active_link_with_a_measurement_is_billable(self) -> None:
        assert is_active(LinkView(), MonthActivity(measurements=1)) is True

    def test_active_link_with_a_message_is_billable(self) -> None:
        assert is_active(LinkView(), MonthActivity(messages=1)) is True

    def test_active_link_with_no_activity_at_all_is_not_billable(self) -> None:
        """The coach must not be charged for a dormant client."""
        assert is_active(LinkView(), MonthActivity()) is False

    @pytest.mark.parametrize(
        "status",
        [LinkStatus.PENDING, LinkStatus.PAUSED, LinkStatus.REVOKED],
    )
    def test_non_active_link_is_never_billable(self, status: LinkStatus) -> None:
        """Even with a full month of activity: the link status gates everything.

        ``paused`` matters most here — it is the RGPD "pause sharing with my coach"
        switch (§5.3). Billing a coach for a client who has withdrawn access would be
        both a billing bug and a bad look under a data-protection audit.
        """
        assert is_active(LinkView(status=status), MonthActivity(workout_logs=20)) is False

    def test_activity_is_combined_with_or_not_and(self) -> None:
        """One signal is enough; requiring all three would under-bill every coach."""
        assert is_active(LinkView(), MonthActivity(workout_logs=1, measurements=0)) is True

    def test_is_a_pure_boolean(self) -> None:
        result = is_active(LinkView(), MonthActivity(workout_logs=1))
        assert isinstance(result, bool), "must be a real bool — it is persisted as one"


class TestDeterminism:
    """The monthly Celery job is specified as idempotent and replayable (§7)."""

    def test_same_inputs_give_the_same_answer(self) -> None:
        link, activity = LinkView(), MonthActivity(workout_logs=3)
        assert is_active(link, activity) == is_active(link, activity)

    def test_does_not_read_the_wall_clock(self) -> None:
        """No hidden ``datetime.now()``: re-running last year's month must be stable.

        If the function consulted the current time, replaying the snapshot job for an old
        period would produce different numbers than the original run — and the whole
        point of ``active_client_snapshot`` is that it is auditable.
        """
        link, activity = LinkView(), MonthActivity(workout_logs=1)
        assert is_active(link, activity, month=date(2026, 9, 1)) is True
        assert is_active(link, activity, month=date(2025, 3, 1)) in (True, False)


class TestOpenQuestions:
    """Recorded, not asserted — the spec does not decide these. See `tech-lead`.

    Each one changes what a coach is invoiced, so leaving them to implementation accident
    is not acceptable. They run green either way; their value is documentary until the
    rule is frozen.
    """

    def test_link_active_only_part_of_the_month(self) -> None:
        """Client revoked mid-month after training for three weeks.

        Charge the full month, prorate, or not at all? ``status`` at the *moment of
        computation* says ``revoked`` and would yield False — meaning a coach who worked
        three weeks bills nothing. That is very likely not intended.
        """
        link = LinkView(status=LinkStatus.REVOKED, ended_at=datetime(2026, 9, 21, tzinfo=UTC))
        outcome = is_active(link, MonthActivity(workout_logs=12))
        assert outcome in (True, False)

    def test_link_created_mid_month(self) -> None:
        link = LinkView(started_at=datetime(2026, 9, 28, tzinfo=UTC))
        assert is_active(link, MonthActivity(workout_logs=1)) in (True, False)

    def test_civil_month_boundary_timezone(self) -> None:
        """Which timezone defines "mois civil"?

        A session logged 2026-10-01 at 00:30 in Paris is 2026-09-30 22:30 UTC. Counted in
        UTC it bills September; counted in Europe/Paris it bills October. Both the
        client-facing product and the invoices are French, so Europe/Paris is the likely
        intent, but the storage is UTC and nothing states the conversion. Whatever is
        chosen must be identical in this function and in the SQL that counts the activity,
        or the snapshot job and the API will disagree.
        """
        assert is_active(LinkView(), MonthActivity(workout_logs=1)) in (True, False)

    def test_trial_month_billability(self) -> None:
        """During the client's free 10-day trial, is the coach already billed?

        §7 defines the trial for the *client* and the commission for the *coach* without
        saying whether they interact.
        """
        assert is_active(LinkView(), MonthActivity(workout_logs=4)) in (True, False)
