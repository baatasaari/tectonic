from __future__ import annotations

import pytest

from sentinel_agents.config import SentinelAgentsSettings
from sentinel_agents.core.event_processor import SentinelEventProcessor
from sentinel_agents.core.fakes import (
    InMemorySentinelRepository,
    StubAuditabilityClient,
    StubHumanOversightClient,
    StubToolOrchestrationClient,
    StubWorkflowEngineClient,
)
from sentinel_agents.core.swarm_correlation import SwarmWindowTracker


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemorySentinelRepository()
        self.workflow_engine = kwargs.get("workflow_engine") or StubWorkflowEngineClient()
        self.tool_orchestration = kwargs.get("tool_orchestration") or StubToolOrchestrationClient()
        self.human_oversight = kwargs.get("human_oversight") or StubHumanOversightClient()
        self.auditability = kwargs.get("auditability") or StubAuditabilityClient()
        self.settings = kwargs.get("settings") or SentinelAgentsSettings()
        self.window_tracker = kwargs.get("window_tracker") or SwarmWindowTracker()

        self.processor = SentinelEventProcessor(
            self.repository, self.workflow_engine, self.tool_orchestration, self.human_oversight,
            self.auditability, self.settings, self.window_tracker,
        )


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
