from __future__ import annotations

import pytest

from agent_cards.core.discovery_service import DiscoveryService
from agent_cards.core.fakes import (
    InMemoryAgentCardsRepository,
    StubEvaluationFrameworkClient,
    StubRegulatoryComplianceClient,
)
from agent_cards.core.registry_service import RegistryService
from agent_cards.core.trust_score_calculator import TrustScoreCalculator


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryAgentCardsRepository()
        self.evaluation_framework = kwargs.get("evaluation_framework") or StubEvaluationFrameworkClient()
        self.regulatory_compliance = kwargs.get("regulatory_compliance") or StubRegulatoryComplianceClient()

        self.registry_service = RegistryService(self.repository)
        self.discovery_service = DiscoveryService(self.repository, staleness_ttl_seconds=kwargs.get("staleness_ttl_seconds", 86400))
        self.trust_score_calculator = TrustScoreCalculator(
            self.repository, self.evaluation_framework, self.regulatory_compliance,
            performance_weight=kwargs.get("performance_weight", 0.6),
            compliance_weight=kwargs.get("compliance_weight", 0.4),
        )


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
