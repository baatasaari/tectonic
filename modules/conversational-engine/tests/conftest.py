from __future__ import annotations

import pytest

from conversational_engine.config import ConversationalEngineSettings
from conversational_engine.core.fakes import (
    InMemoryAuditabilityClient,
    InMemoryConversationRepository,
    InMemoryObservabilityClient,
    InMemorySessionStateStore,
    StubGuardrailsClient,
    StubHumanOversightClient,
    StubLLMGatewayClient,
    StubWorkflowEngineClient,
)
from conversational_engine.core.session_manager import SessionManager


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryConversationRepository()
        self.state_store = InMemorySessionStateStore()
        self.llm_gateway = kwargs.get("llm_gateway") or StubLLMGatewayClient()
        self.guardrails = kwargs.get("guardrails") or StubGuardrailsClient()
        self.human_oversight = StubHumanOversightClient()
        self.observability = InMemoryObservabilityClient()
        self.auditability = InMemoryAuditabilityClient()
        self.settings = kwargs.get("settings") or ConversationalEngineSettings()
        self.workflow_engine = kwargs.get("workflow_engine") or StubWorkflowEngineClient()

        self.manager = SessionManager(
            repository=self.repository,
            state_store=self.state_store,
            llm_gateway=self.llm_gateway,
            guardrails=self.guardrails,
            human_oversight=self.human_oversight,
            observability=self.observability,
            auditability=self.auditability,
            settings=self.settings,
            workflow_engine=self.workflow_engine,
        )


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
