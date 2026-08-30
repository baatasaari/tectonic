from __future__ import annotations

import pytest

from promptops.core.ab_testing_service import ABTestingService
from promptops.core.drift_detection_service import DriftDetectionService
from promptops.core.fakes import (
    InMemoryPromptOpsRepository,
    StubEvaluationFrameworkClient,
    StubLLMGatewayClient,
)
from promptops.core.prompt_registry_service import PromptRegistryService
from promptops.core.reflection_optimiser import ReflectionOptimiser


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryPromptOpsRepository()
        self.evaluation_framework = kwargs.get("evaluation_framework") or StubEvaluationFrameworkClient()
        self.llm_gateway = kwargs.get("llm_gateway") or StubLLMGatewayClient()

        self.prompt_registry_service = PromptRegistryService(self.repository)
        self.ab_testing_service = ABTestingService(
            self.repository, self.evaluation_framework,
            min_sample_size_per_arm=kwargs.get("min_sample_size_per_arm", 3),
            significance_level=kwargs.get("significance_level", 0.05),
        )
        self.drift_detection_service = DriftDetectionService(
            self.repository, self.evaluation_framework,
            significance_level=kwargs.get("drift_significance_level", 0.05),
        )
        self.reflection_optimiser = ReflectionOptimiser(
            self.repository, self.evaluation_framework, self.llm_gateway,
            max_pass_rate_before_reflection=kwargs.get("max_pass_rate_before_reflection", 0.9),
            min_reflection_sample_size=kwargs.get("min_reflection_sample_size", 3),
            reflection_model=kwargs.get("reflection_model", "gpt-4o-mini"),
        )


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
