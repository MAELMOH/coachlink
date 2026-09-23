"""The under-16 signup refusal (ARCHITECTURE.md §5.2).

Boundary-heavy by design: the interesting failures are all off-by-one-day, and a naive
``reference.year - birth.year`` passes every "obviously too young" test while wrongly
admitting a 15-year-old whose birthday falls later in the year.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.age import age_on, is_old_enough

MINIMUM_AGE = 16


class TestAgeOn:
    def test_birthday_not_yet_reached_this_year(self) -> None:
        """Born in December, measured in January: still the younger age."""
        assert age_on(date(2010, 12, 31), date(2026, 1, 1)) == 15

    def test_on_the_birthday_the_age_ticks_over(self) -> None:
        assert age_on(date(2010, 6, 15), date(2026, 6, 15)) == 16

    def test_the_day_before_the_birthday(self) -> None:
        assert age_on(date(2010, 6, 15), date(2026, 6, 14)) == 15

    def test_born_today(self) -> None:
        assert age_on(date(2026, 9, 23), date(2026, 9, 23)) == 0

    def test_leap_day_birthday_in_a_non_leap_year(self) -> None:
        """29 February 2008 + 16 years. In 2024 (a leap year) the birthday exists; the
        rule must still be total for non-leap years, where 1 March is the first day the
        person counts as older."""
        assert age_on(date(2008, 2, 29), date(2026, 2, 28)) == 17
        assert age_on(date(2008, 2, 29), date(2026, 3, 1)) == 18


class TestMinimumAge:
    @pytest.mark.parametrize(
        ("birth", "reference", "expected"),
        [
            (date(2010, 9, 23), date(2026, 9, 23), True),  # exactly 16 today
            (date(2010, 9, 24), date(2026, 9, 23), False),  # 16 tomorrow
            (date(2009, 1, 1), date(2026, 9, 23), True),
            (date(2011, 1, 1), date(2026, 9, 23), False),
        ],
    )
    def test_boundaries(self, birth: date, reference: date, expected: bool) -> None:
        assert is_old_enough(birth, reference, MINIMUM_AGE) is expected

    def test_the_rule_is_under_16_refused_not_under_17(self) -> None:
        """Guards against an off-by-one that would refuse legitimate 16-year-olds."""
        assert is_old_enough(date(2010, 9, 23), date(2026, 9, 23), MINIMUM_AGE)
