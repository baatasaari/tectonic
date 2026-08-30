"""Abstract ports this module depends on: persistence, and the real LLM
Gateway peer client the Usage Aggregation Service reads live spend from.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from finops.core.domain import BudgetPolicyRecord, OptimisationActionRecord, UsageEventRecord


class FinOpsRepository(Protocol):
    async def create_usage_event(self, record: UsageEventRecord) -> UsageEventRecord: ...

    async def sum_usage_cost(self, *, tenant_id: str, start: datetime, end: datetime) -> float:
        """Sum of `cost` across every UsageEventRecord for this tenant in
        `[start, end)`. LLM Gateway never reports events here (its spend
        is read live instead), so this sum is never at risk of
        double-counting LLM spend."""
        ...

    async def create_budget_policy(self, record: BudgetPolicyRecord) -> BudgetPolicyRecord: ...

    async def get_budget_policy(self, budget_policy_id: str) -> BudgetPolicyRecord | None: ...

    async def update_budget_policy(self, record: BudgetPolicyRecord) -> BudgetPolicyRecord: ...

    async def create_optimisation_action(self, record: OptimisationActionRecord) -> OptimisationActionRecord: ...

    async def list_optimisation_actions(
        self, *, budget_policy_id: str, limit: int = 50, offset: int = 0,
    ) -> tuple[list[OptimisationActionRecord], int]: ...


class LLMGatewaySpendClient(Protocol):
    async def tenant_spend(self, tenant_id: str) -> float:
        """Sums `current_spend` across every distinct budget policy
        referenced by the tenant's virtual keys, per LLM Gateway's own
        `GET /admin/virtual-keys` + `GET /admin/budgets/{id}`. 0.0, not
        an error, when the tenant has no virtual keys registered yet."""
        ...
