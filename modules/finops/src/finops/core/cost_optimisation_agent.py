"""Cost Optimisation Agent (LLD §2 sub-components, §Level 3 "Sequence: a
bounded autonomous action"): the one autonomous action this module
takes -- tightening a budget's `alert_threshold_pct`, one configured
step at a time, never below a configured floor, and always logged with
its reason. Never blocks spend, never touches LLM Gateway's own hard
budget enforcement.
"""
from __future__ import annotations

from finops.core.domain import OptimisationActionRecord, new_id
from finops.core.forecasting_service import ForecastingService
from finops.core.ports import FinOpsRepository
from finops.core.usage_aggregation_service import UsageAggregationService

_ACTION_LOWERED_ALERT_THRESHOLD = "lowered_alert_threshold"


class CostOptimisationAgent:
    def __init__(
        self, repository: FinOpsRepository, usage_aggregation: UsageAggregationService,
        forecasting: ForecastingService, *, min_alert_threshold_pct: float = 0.5, alert_threshold_step: float = 0.05,
    ) -> None:
        self._repository = repository
        self._usage_aggregation = usage_aggregation
        self._forecasting = forecasting
        self._min_alert_threshold_pct = min_alert_threshold_pct
        self._alert_threshold_step = alert_threshold_step

    async def evaluate(self, budget_policy) -> OptimisationActionRecord | None:
        """Returns the action taken, or `None` if no action was warranted
        (insufficient data to forecast yet, forecast within bounds, or the
        policy is already at its configured floor)."""
        report = await self._usage_aggregation.cost_report(
            tenant_id=budget_policy.tenant_id, period=budget_policy.period, budget_policy=budget_policy,
        )
        forecast = self._forecasting.forecast(period=budget_policy.period, total_cost_so_far=report.total_cost)

        if forecast is None or forecast <= budget_policy.limit_amount:
            return None
        if budget_policy.alert_threshold_pct <= self._min_alert_threshold_pct:
            return None

        previous_value = budget_policy.alert_threshold_pct
        new_value = max(self._min_alert_threshold_pct, previous_value - self._alert_threshold_step)

        budget_policy.alert_threshold_pct = new_value
        await self._repository.update_budget_policy(budget_policy)

        return await self._repository.create_optimisation_action(
            OptimisationActionRecord(
                id=new_id(), tenant_id=budget_policy.tenant_id, budget_policy_id=budget_policy.id,
                action_type=_ACTION_LOWERED_ALERT_THRESHOLD, previous_value=previous_value, new_value=new_value,
                reason=f"forecast {forecast:.2f} exceeds budget limit {budget_policy.limit_amount:.2f}",
            )
        )
