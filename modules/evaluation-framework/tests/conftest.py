from __future__ import annotations

import pytest

from evaluation_framework.core.evaluator import Evaluator
from evaluation_framework.core.fakes import (
    InMemoryEvaluationFrameworkRepository,
    StubLLMGatewayClient,
)
from evaluation_framework.core.gate_engine import GateEngine
from evaluation_framework.core.sampler import ProductionSampler


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryEvaluationFrameworkRepository()
        self.llm_gateway = kwargs.get("llm_gateway") or StubLLMGatewayClient()
        self.thresholds = kwargs.get("thresholds") or {
            "faithfulness": 0.5, "coherence": 0.5, "tool_trace_correctness": 0.9, "financial_guidance_compliance": 1.0,
        }

        self.evaluator = Evaluator(self.repository, self.llm_gateway, self.thresholds)
        self.gate_engine = GateEngine(self.repository)
        self.sampler = ProductionSampler(kwargs.get("sample_rate", 0.5))


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
