import pytest

from llm_gateway.config import BudgetConfig
from llm_gateway.core.cost_governance import CostGovernanceEngine
from llm_gateway.core.domain import BudgetExceededError, BudgetPeriod, BudgetPolicyRecord, new_id
from llm_gateway.core.fakes import InMemoryGatewayRepository

pytestmark = pytest.mark.asyncio


async def _make_policy(repo, limit_amount, current_spend=0.0):
    return await repo.create_budget_policy(
        BudgetPolicyRecord(
            id=new_id(), tenant_id="tenant-a", period=BudgetPeriod.MONTHLY,
            limit_amount=limit_amount, current_spend=current_spend,
        )
    )


async def test_reserve_within_budget_succeeds():
    repo = InMemoryGatewayRepository()
    policy = await _make_policy(repo, limit_amount=10.0)
    engine = CostGovernanceEngine(repo, BudgetConfig(enforce_hard_limit=True))

    updated = await engine.check_and_reserve_budget(policy.id)

    assert updated.current_spend > policy.current_spend


async def test_reserve_over_hard_limit_rejected():
    repo = InMemoryGatewayRepository()
    policy = await _make_policy(repo, limit_amount=0.1, current_spend=0.09)
    engine = CostGovernanceEngine(repo, BudgetConfig(enforce_hard_limit=True))

    with pytest.raises(BudgetExceededError):
        await engine.check_and_reserve_budget(policy.id)


async def test_soft_limit_never_blocks():
    repo = InMemoryGatewayRepository()
    policy = await _make_policy(repo, limit_amount=0.01, current_spend=0.5)
    engine = CostGovernanceEngine(repo, BudgetConfig(enforce_hard_limit=False))

    updated = await engine.check_and_reserve_budget(policy.id)
    assert updated is not None  # did not raise


async def test_settle_replaces_estimate_with_actual_cost():
    repo = InMemoryGatewayRepository()
    policy = await _make_policy(repo, limit_amount=10.0)
    engine = CostGovernanceEngine(repo, BudgetConfig(enforce_hard_limit=True))

    await engine.check_and_reserve_budget(policy.id)
    settled = await engine.settle(policy.id, actual_cost=0.01)

    assert settled.current_spend == pytest.approx(0.01, abs=1e-9)


async def test_utilisation_ratio():
    repo = InMemoryGatewayRepository()
    policy = await _make_policy(repo, limit_amount=10.0, current_spend=5.0)
    engine = CostGovernanceEngine(repo, BudgetConfig())
    assert engine.utilisation_ratio(policy) == pytest.approx(0.5)
