from __future__ import annotations

import pytest

from tool_orchestration.config import (
    CircuitBreakerConfig,
    RetryConfig,
    SynthesisConfig,
    ToolOrchestrationSettings,
)
from tool_orchestration.core.circuit_breaker import CircuitBreaker
from tool_orchestration.core.fakes import (
    FakeMCPClientAdapter,
    InMemoryCircuitBreakerStore,
    InMemoryToolRepository,
    StubGuardrailsClient,
    StubLLMGatewayClient,
    StubSentinelAgentsClient,
)
from tool_orchestration.core.orchestration_service import ToolOrchestrationService
from tool_orchestration.core.reliability_scorer import ReliabilityScorer
from tool_orchestration.core.retry_manager import RetryManager
from tool_orchestration.core.tool_synthesis import ToolSynthesisEngine


async def _noop_sleep(_seconds: float) -> None:
    return None


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryToolRepository()
        self.circuit_breaker_store = InMemoryCircuitBreakerStore()
        self.mcp_client = kwargs.get("mcp_client") or FakeMCPClientAdapter()
        self.llm_gateway = kwargs.get("llm_gateway") or StubLLMGatewayClient()
        self.guardrails = kwargs.get("guardrails") or StubGuardrailsClient()
        self.sentinel = StubSentinelAgentsClient()
        self.settings = kwargs.get("settings") or ToolOrchestrationSettings(
            circuit_breaker=kwargs.get("circuit_breaker_config") or CircuitBreakerConfig(),
            retry=kwargs.get("retry_config") or RetryConfig(),
            synthesis=kwargs.get("synthesis_config") or SynthesisConfig(),
        )

        self.circuit_breaker = CircuitBreaker(self.settings.circuit_breaker)
        self.retry_manager = RetryManager(self.mcp_client, self.settings.retry, sleep_fn=_noop_sleep, backoff_base_seconds=0.0)
        self.reliability_scorer = ReliabilityScorer()
        self.service = ToolOrchestrationService(
            self.repository, self.circuit_breaker_store, self.circuit_breaker, self.retry_manager, self.reliability_scorer
        )
        self.synthesis_engine = ToolSynthesisEngine(
            self.repository, self.llm_gateway, self.guardrails, self.sentinel, self.settings.synthesis
        )


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
