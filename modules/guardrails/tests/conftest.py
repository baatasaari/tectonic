from __future__ import annotations

import pytest

from guardrails.config import RedTeamConfig
from guardrails.core.domain import PolicyProfileRecord, new_id
from guardrails.core.fakes import (
    InMemoryGuardrailsRepository,
    StubLLMGatewayClient,
    StubSentinelAgentsClient,
)
from guardrails.core.policy_engine import PolicyEngine
from guardrails.core.red_team import RedTeamRunner


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryGuardrailsRepository()
        self.llm_gateway = kwargs.get("llm_gateway") or StubLLMGatewayClient()
        self.sentinel = kwargs.get("sentinel") or StubSentinelAgentsClient()
        self.red_team_config = kwargs.get("red_team_config") or RedTeamConfig()

        self.policy_engine = PolicyEngine(self.llm_gateway)
        self.red_team_runner = RedTeamRunner(
            self.repository, self.policy_engine, self.llm_gateway, self.sentinel,
            self.red_team_config.attempts_per_run,
        )

    def default_profile(self, tenant_id: str = "t1", **overrides) -> PolicyProfileRecord:
        kwargs = {
            "id": new_id(), "tenant_id": tenant_id, "name": "default",
            "enabled_checks": ["pii_detection", "jailbreak_detection", "groundedness_check"],
            "pii_entity_types": ["EMAIL", "PHONE_NUMBER", "PERSON", "CREDIT_CARD"],
        }
        kwargs.update(overrides)
        return PolicyProfileRecord(**kwargs)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
