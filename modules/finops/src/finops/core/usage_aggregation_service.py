"""Usage Aggregation Service (LLD §2 sub-components): combines LLM
Gateway's own live spend with this module's own ingested usage events
into one `CostReport` per tenant/period.
"""
from __future__ import annotations

from finops.core.domain import BudgetPeriod, CostReport, now, period_window
from finops.core.ports import FinOpsRepository, LLMGatewaySpendClient


class UsageAggregationService:
    def __init__(self, repository: FinOpsRepository, llm_gateway: LLMGatewaySpendClient) -> None:
        self._repository = repository
        self._llm_gateway = llm_gateway

    async def cost_report(self, *, tenant_id: str, period: BudgetPeriod, budget_policy=None) -> CostReport:
        start, end = period_window(period, now())

        llm_gateway_spend = await self._llm_gateway.tenant_spend(tenant_id)
        other_usage_cost = await self._repository.sum_usage_cost(tenant_id=tenant_id, start=start, end=end)
        total_cost = llm_gateway_spend + other_usage_cost

        utilisation_ratio = None
        alert = False
        if budget_policy is not None and budget_policy.limit_amount > 0:
            utilisation_ratio = total_cost / budget_policy.limit_amount
            alert = utilisation_ratio >= budget_policy.alert_threshold_pct

        return CostReport(
            tenant_id=tenant_id, period=period, llm_gateway_spend=llm_gateway_spend, other_usage_cost=other_usage_cost,
            total_cost=total_cost, forecast_amount=None, budget_policy=budget_policy,
            utilisation_ratio=utilisation_ratio, alert=alert,
        )
