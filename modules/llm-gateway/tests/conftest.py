from __future__ import annotations

import pytest

from llm_gateway.config import LLMGatewaySettings
from llm_gateway.core.cost_governance import CostGovernanceEngine
from llm_gateway.core.domain import BudgetPeriod, BudgetPolicyRecord, VirtualKeyRecord, new_id
from llm_gateway.core.failover import FailoverManager
from llm_gateway.core.fakes import (
    FakeProviderClient,
    FakeQualityScoreProvider,
    InMemoryGatewayRepository,
)
from llm_gateway.core.gateway_service import LLMGatewayService
from llm_gateway.core.router import QualityAwareRouter
from llm_gateway.core.semantic_cache import InMemorySemanticCache


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryGatewayRepository()
        self.cache = kwargs.get("cache") or InMemorySemanticCache(
            similarity_threshold=kwargs.get("similarity_threshold", 0.92)
        )
        self.quality_scores = kwargs.get("quality_scores") or FakeQualityScoreProvider()
        self.provider_client = kwargs.get("provider_client") or FakeProviderClient()
        self.settings = kwargs.get("settings") or LLMGatewaySettings()

        self.router = QualityAwareRouter(self.quality_scores, self.settings.routing)
        self.cost_governance = CostGovernanceEngine(self.repository, self.settings.budget)
        self.failover = FailoverManager(self.provider_client, self.settings.failover.max_provider_attempts)
        self.service = LLMGatewayService(
            self.repository, self.cache, self.router, self.cost_governance, self.failover, self.settings
        )

    async def seed_tenant(
        self, tenant_id: str = "tenant-a", limit_amount: float = 100.0, provider_scope: list[str] | None = None
    ) -> VirtualKeyRecord:
        budget = await self.repository.create_budget_policy(
            BudgetPolicyRecord(id=new_id(), tenant_id=tenant_id, period=BudgetPeriod.MONTHLY, limit_amount=limit_amount)
        )
        vk = await self.repository.create_virtual_key(
            VirtualKeyRecord(
                id=new_id(), tenant_id=tenant_id, provider_scope=provider_scope or [], budget_policy_ref=budget.id
            )
        )
        return vk


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
