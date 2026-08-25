"""In-memory fakes for unit tests (LLD "Deployability and testability
contract")."""
from __future__ import annotations

from datetime import datetime

from finops.core.domain import BudgetPolicyRecord, OptimisationActionRecord, UsageEventRecord


class InMemoryFinOpsRepository:
    def __init__(self) -> None:
        self.usage_events: list[UsageEventRecord] = []
        self.budget_policies: dict[str, BudgetPolicyRecord] = {}
        self.optimisation_actions: list[OptimisationActionRecord] = []

    async def create_usage_event(self, record: UsageEventRecord) -> UsageEventRecord:
        self.usage_events.append(record)
        return record

    async def sum_usage_cost(self, *, tenant_id: str, start: datetime, end: datetime) -> float:
        return sum(
            e.cost for e in self.usage_events
            if e.tenant_id == tenant_id and start <= e.occurred_at < end
        )

    async def create_budget_policy(self, record: BudgetPolicyRecord) -> BudgetPolicyRecord:
        self.budget_policies[record.id] = record
        return record

    async def get_budget_policy(self, budget_policy_id: str) -> BudgetPolicyRecord | None:
        return self.budget_policies.get(budget_policy_id)

    async def update_budget_policy(self, record: BudgetPolicyRecord) -> BudgetPolicyRecord:
        self.budget_policies[record.id] = record
        return record

    async def create_optimisation_action(self, record: OptimisationActionRecord) -> OptimisationActionRecord:
        self.optimisation_actions.append(record)
        return record

    async def list_optimisation_actions(
        self, *, budget_policy_id: str, limit: int = 50, offset: int = 0,
    ) -> tuple[list[OptimisationActionRecord], int]:
        results = sorted(
            (a for a in self.optimisation_actions if a.budget_policy_id == budget_policy_id),
            key=lambda a: a.taken_at,
        )
        return results[offset:offset + limit], len(results)


class StubLLMGatewaySpendClient:
    def __init__(self, *, spend: float = 0.0) -> None:
        self.calls: list[dict] = []
        self._spend = spend

    async def tenant_spend(self, tenant_id: str) -> float:
        self.calls.append({"tenant_id": tenant_id})
        return self._spend


__all__ = ["InMemoryFinOpsRepository", "StubLLMGatewaySpendClient"]
