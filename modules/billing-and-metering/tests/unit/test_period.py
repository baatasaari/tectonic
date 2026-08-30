"""Tests for core/period.py -- pure, deterministic, no fake needed."""
from __future__ import annotations

from datetime import UTC, datetime

from billing_and_metering.core.period import period_window


def test_daily_window_is_midnight_to_midnight():
    at = datetime(2026, 3, 15, 14, 30, tzinfo=UTC)

    start, end = period_window("daily", at)

    assert start == datetime(2026, 3, 15, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 3, 16, 0, 0, tzinfo=UTC)


def test_monthly_window_is_first_of_month_to_first_of_next_month():
    at = datetime(2026, 3, 15, 14, 30, tzinfo=UTC)

    start, end = period_window("monthly", at)

    assert start == datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 4, 1, 0, 0, tzinfo=UTC)


def test_monthly_window_rolls_over_the_year_in_december():
    at = datetime(2026, 12, 15, tzinfo=UTC)

    start, end = period_window("monthly", at)

    assert start == datetime(2026, 12, 1, tzinfo=UTC)
    assert end == datetime(2027, 1, 1, tzinfo=UTC)
