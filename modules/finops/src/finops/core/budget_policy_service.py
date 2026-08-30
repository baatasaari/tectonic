"""Budget Policy Service (LLD §2 sub-components): CRUD for this module's
own, platform-wide budget policies -- distinct from LLM Gateway's own
request-time budget enforcement (LLD §Level 1's own boundary note).
"""
from __future__ import annotations

from finops.core.domain import BudgetPeriod, BudgetPolicyNotFoundError, BudgetPolicyRecord, new_id
from finops.core.ports import FinOpsRepository


class BudgetPolicyService:
    def __init__(self, repository: FinOpsRepository) -> None:
        self._repository = repository

    async def create(
        self, *, tenant_id: str, period: BudgetPeriod, limit_amount: float, alert_threshold_pct: float = 0.8,
    ) -> BudgetPolicyRecord:
        record = BudgetPolicyRecord(
            id=new_id(), tenant_id=tenant_id, period=period, limit_amount=limit_amount,
            alert_threshold_pct=alert_threshold_pct,
        )
        return await self._repository.create_budget_policy(record)

    async def get(self, budget_policy_id: str) -> BudgetPolicyRecord:
        record = await self._repository.get_budget_policy(budget_policy_id)
        if record is None:
            raise BudgetPolicyNotFoundError(budget_policy_id)
        return record
