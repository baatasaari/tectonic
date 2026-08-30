from __future__ import annotations

import pytest

from workflow_engine.config import ExecutionConfig, ReplanningConfig
from workflow_engine.core.fakes import (
    InMemoryEventPublisher,
    InMemoryWorkflowRepository,
    StubAgenticRAGClient,
    StubGuardrailsClient,
    StubHumanOversightClient,
    StubIntentDetectionClient,
    StubLLMGatewayClient,
    StubToolOrchestrationClient,
)
from workflow_engine.core.human import HumanApprovalHandler
from workflow_engine.core.neural import NeuralStepExecutor
from workflow_engine.core.replanner import Replanner
from workflow_engine.core.scheduler import ExecutionScheduler
from workflow_engine.core.symbolic import SymbolicRuleExecutor


class Harness:
    """Bundles a scheduler with all its in-memory fakes for assertions."""

    def __init__(self, **kwargs):
        self.repository = InMemoryWorkflowRepository()
        self.event_publisher = InMemoryEventPublisher()
        self.symbolic_executor = SymbolicRuleExecutor()
        self.llm_gateway = StubLLMGatewayClient(default_confidence=kwargs.get("default_confidence", 0.95))
        self.tool_orchestration = StubToolOrchestrationClient()
        self.guardrails = kwargs.get("guardrails") or StubGuardrailsClient()
        self.human_oversight = StubHumanOversightClient()
        self.intent_detection = kwargs.get("intent_detection") or StubIntentDetectionClient()
        self.agentic_rag = kwargs.get("agentic_rag") or StubAgenticRAGClient()

        neural_executor = NeuralStepExecutor(
            self.llm_gateway, self.tool_orchestration, self.guardrails,
            intent_detection=self.intent_detection, agentic_rag=self.agentic_rag,
        )
        human_handler = HumanApprovalHandler(self.repository, self.human_oversight)
        replanner = Replanner(self.repository, self.llm_gateway)

        self.scheduler = ExecutionScheduler(
            repository=self.repository,
            event_publisher=self.event_publisher,
            symbolic_executor=self.symbolic_executor,
            neural_executor=neural_executor,
            human_handler=human_handler,
            replanner=replanner,
            execution_config=kwargs.get("execution_config") or ExecutionConfig(max_parallel_steps_per_instance=10),
            replanning_config=kwargs.get("replanning_config") or ReplanningConfig(enabled=True),
            sleep_fn=_noop_sleep,
            backoff_base_seconds=0.0,
        )


async def _noop_sleep(_seconds: float) -> None:
    return None


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
