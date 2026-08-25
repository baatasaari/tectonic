from __future__ import annotations

import pytest

from finops.core.budget_policy_service import BudgetPolicyService
from finops.core.cost_optimisation_agent import CostOptimisationAgent
from finops.core.fakes import InMemoryFinOpsRepository, StubLLMGatewaySpendClient
from finops.core.forecasting_service import ForecastingService
from finops.core.usage_aggregation_service import UsageAggregationService


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryFinOpsRepository()
        self.llm_gateway = kwargs.get("llm_gateway") or StubLLMGatewaySpendClient()

        self.budget_policy_service = BudgetPolicyService(self.repository)
        self.usage_aggregation_service = UsageAggregationService(self.repository, self.llm_gateway)
        self.forecasting_service = ForecastingService()
        self.cost_optimisation_agent = CostOptimisationAgent(
            self.repository, self.usage_aggregation_service, self.forecasting_service,
            min_alert_threshold_pct=kwargs.get("min_alert_threshold_pct", 0.5),
            alert_threshold_step=kwargs.get("alert_threshold_step", 0.05),
        )


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
