"""Tests for core/forecasting_service.py -- a run-rate forecast of
period-end spend, honest about insufficient data early in a period."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from finops.core.domain import BudgetPeriod
from finops.core.forecasting_service import ForecastingService


def _at(dt: datetime):
    return patch("finops.core.forecasting_service.now", return_value=dt)


def test_forecast_returns_none_when_too_little_of_the_period_has_elapsed():
    service = ForecastingService()
    # 1 hour into a 30-day month is far below the 5% floor.
    with _at(datetime(2026, 3, 1, 1, 0, tzinfo=UTC)):
        result = service.forecast(period=BudgetPeriod.MONTHLY, total_cost_so_far=10.0)

    assert result is None


def test_forecast_projects_period_end_spend_from_run_rate():
    service = ForecastingService()
    # Exactly half of a 30-day (Jan) month elapsed, $50 spent so far -> $100 projected.
    with _at(datetime(2026, 1, 16, 0, 0, tzinfo=UTC)):
        result = service.forecast(period=BudgetPeriod.MONTHLY, total_cost_so_far=50.0)

    assert result is not None
    assert 95.0 <= result <= 105.0


def test_forecast_for_daily_period_uses_the_daily_window():
    service = ForecastingService()
    start = datetime(2026, 3, 1, tzinfo=UTC)
    with _at(start + timedelta(hours=12)):
        result = service.forecast(period=BudgetPeriod.DAILY, total_cost_so_far=5.0)

    assert result is not None
    assert 9.0 <= result <= 11.0
