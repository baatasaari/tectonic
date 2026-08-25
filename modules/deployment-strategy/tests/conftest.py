from __future__ import annotations

import pytest

from deployment_strategy.core.canary_health_calculator import CanaryHealthCalculator
from deployment_strategy.core.fakes import (
    InMemoryDeploymentStrategyRepository,
    StubEvaluationFrameworkClient,
    StubFinOpsClient,
)
from deployment_strategy.core.rollout_service import RolloutService


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryDeploymentStrategyRepository()
        self.evaluation_framework = kwargs.get("evaluation_framework") or StubEvaluationFrameworkClient()
        self.finops = kwargs.get("finops") or StubFinOpsClient()

        self.canary_health_calculator = CanaryHealthCalculator(
            self.evaluation_framework, self.finops,
            min_groundedness_sample_size=kwargs.get("min_groundedness_sample_size", 3),
            min_health_score=kwargs.get("min_health_score", 0.8),
            groundedness_weight=kwargs.get("groundedness_weight", 0.6),
            cost_weight=kwargs.get("cost_weight", 0.4),
            budget_period=kwargs.get("budget_period", "monthly"),
        )
        self.rollout_service = RolloutService(self.repository, self.canary_health_calculator)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
