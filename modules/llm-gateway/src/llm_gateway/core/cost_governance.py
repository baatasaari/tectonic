"""Cost Governance Engine (LLD §2.2, §3.4): checks and reserves budget
before allowing a call, settles against actual cost afterward. Postgres
transactional budget table via the repository port.
"""
from __future__ import annotations

from llm_gateway.config import BudgetConfig
from llm_gateway.core.domain import BudgetExceededError, BudgetPolicyRecord
from llm_gateway.core.ports import GatewayRepository

# Reasonable upper-bound estimate used to pre-authorize a call before its
# real cost is known; refined to the actual cost once the provider responds.
_ESTIMATED_COST_CEILING = 0.50


class CostGovernanceEngine:
    def __init__(self, repository: GatewayRepository, config: BudgetConfig) -> None:
        self.repository = repository
        self.config = config

    async def check_and_reserve_budget(self, budget_policy_id: str) -> BudgetPolicyRecord:
        """Raises BudgetExceededError if the estimated cost would breach a
        hard limit; otherwise reserves the estimate and returns the updated
        policy. A soft-limit tenant (enforce_hard_limit=False) is never
        blocked — only alerted via the budget-utilisation metric."""
        policy = await self.repository.get_budget_policy(budget_policy_id)
        if policy is None:
            raise LookupError(budget_policy_id)

        projected = policy.current_spend + _ESTIMATED_COST_CEILING
        if self.config.enforce_hard_limit and projected > policy.limit_amount:
            raise BudgetExceededError(
                f"budget policy {budget_policy_id} would exceed its limit ({projected:.4f} > {policy.limit_amount:.4f})"
            )

        return await self.repository.update_budget_spend(budget_policy_id, min(projected, policy.limit_amount * 10))

    async def settle(self, budget_policy_id: str, actual_cost: float) -> BudgetPolicyRecord:
        """Replace the optimistic reservation with the real cost: subtract
        the estimate back out, add what was actually spent."""
        policy = await self.repository.get_budget_policy(budget_policy_id)
        if policy is None:
            raise LookupError(budget_policy_id)
        settled = policy.current_spend - _ESTIMATED_COST_CEILING + actual_cost
        return await self.repository.update_budget_spend(budget_policy_id, max(settled, 0.0))

    def utilisation_ratio(self, policy: BudgetPolicyRecord) -> float:
        if policy.limit_amount <= 0:
            return 0.0
        return policy.current_spend / policy.limit_amount
