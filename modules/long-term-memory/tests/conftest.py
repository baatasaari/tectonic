from __future__ import annotations

import pytest

from long_term_memory.config import ConsolidationConfig, CrossAgentSharingConfig
from long_term_memory.core.consolidation import ConsolidationEngine
from long_term_memory.core.fakes import (
    InMemoryLongTermMemoryRepository,
    StubGraphDBClient,
    StubGuardrailsClient,
    StubLLMGatewayClient,
    StubVectorDBClient,
)
from long_term_memory.core.forgetting import ForgettingEngine
from long_term_memory.core.memory_service import MemoryService
from long_term_memory.core.reflection import ReflectionLoop


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryLongTermMemoryRepository()
        self.vector_db = kwargs.get("vector_db") or StubVectorDBClient()
        self.graph_db = kwargs.get("graph_db") or StubGraphDBClient()
        self.llm_gateway = kwargs.get("llm_gateway") or StubLLMGatewayClient()
        self.guardrails = kwargs.get("guardrails") or StubGuardrailsClient()
        self.cross_agent_config = kwargs.get("cross_agent_config") or CrossAgentSharingConfig()
        self.consolidation_config = kwargs.get("consolidation_config") or ConsolidationConfig()

        self.memory_service = MemoryService(
            self.repository, self.vector_db, self.graph_db, self.guardrails, self.cross_agent_config,
        )
        self.consolidation_engine = ConsolidationEngine(self.repository, self.consolidation_config.decay_threshold)
        self.forgetting_engine = ForgettingEngine(self.repository, self.vector_db, self.graph_db)
        self.reflection_loop = ReflectionLoop(self.repository, self.llm_gateway)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
