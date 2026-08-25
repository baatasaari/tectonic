"""Forecasting Service (LLD §2 sub-components): a run-rate projection of
period-end spend from the fraction of the period already elapsed.
Returns `None` -- not a wild extrapolation -- when too little of the
period has elapsed to say anything useful, the same insufficient-data
honesty this platform's own Agent Cards and LLMOps trust/gate
calculators already established for their own real-signal computations.
"""
from __future__ import annotations

from finops.core.domain import BudgetPeriod, now, period_window

# Below this fraction of the period elapsed, a run-rate projection amplifies noise by
# more than 20x (1 / 0.05) -- not a forecast, a guess dressed as one.
_MIN_ELAPSED_FRACTION = 0.05


class ForecastingService:
    def forecast(self, *, period: BudgetPeriod, total_cost_so_far: float) -> float | None:
        at = now()
        start, end = period_window(period, at)
        elapsed_fraction = (at - start).total_seconds() / (end - start).total_seconds()

        if elapsed_fraction < _MIN_ELAPSED_FRACTION:
            return None

        return total_cost_so_far / elapsed_fraction
