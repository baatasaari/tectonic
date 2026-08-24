from __future__ import annotations

import pytest

from agent_marketplace.core.catalogue_service import CatalogueService
from agent_marketplace.core.catalogue_sync_service import CatalogueSyncService
from agent_marketplace.core.fakes import InMemoryAgentMarketplaceRepository, StubAgentCardsClient
from agent_marketplace.core.governance_service import GovernanceService
from agent_marketplace.core.usage_tracking_service import UsageTrackingService


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryAgentMarketplaceRepository()
        self.agent_cards = kwargs.get("agent_cards") or StubAgentCardsClient()

        self.governance_service = GovernanceService(self.repository, self.agent_cards)
        self.catalogue_sync_service = CatalogueSyncService(self.repository, self.agent_cards)
        self.catalogue_service = CatalogueService(self.repository)
        self.usage_tracking_service = UsageTrackingService(self.repository)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
