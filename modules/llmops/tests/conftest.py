from __future__ import annotations

import pytest

from llmops.core.canary_evaluation_service import CanaryEvaluationService
from llmops.core.fakes import InMemoryLLMOpsRepository, StubEvaluationFrameworkClient
from llmops.core.model_registry_service import ModelRegistryService
from llmops.core.rollout_service import RolloutService


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryLLMOpsRepository()
        self.evaluation_framework = kwargs.get("evaluation_framework") or StubEvaluationFrameworkClient()

        self.model_registry_service = ModelRegistryService(self.repository)
        self.canary_evaluation_service = CanaryEvaluationService(
            self.evaluation_framework, min_sample_size=kwargs.get("min_sample_size", 3),
            min_pass_rate=kwargs.get("min_pass_rate", 0.8),
        )
        self.rollout_service = RolloutService(
            self.repository, self.canary_evaluation_service, self.evaluation_framework,
        )


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
