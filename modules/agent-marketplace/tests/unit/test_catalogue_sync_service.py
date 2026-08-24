"""Tests for core/catalogue_sync_service.py -- wholesale replace, never a merge."""
from __future__ import annotations

import pytest

from agent_marketplace.core.domain import AgentCardNotFoundError, ListingNotFoundError
from agent_marketplace.core.fakes import StubAgentCardsClient


async def test_sync_raises_for_an_unknown_listing(harness):
    with pytest.raises(ListingNotFoundError):
        await harness.catalogue_sync_service.sync("does-not-exist")


async def test_sync_raises_when_the_referenced_card_no_longer_exists(harness_factory):
    agent_cards = StubAgentCardsClient()
    harness = harness_factory(agent_cards=agent_cards)
    listing = await harness.governance_service.submit(tenant_id="acme", agent_card_id="card-1", submitted_by="alice")
    agent_cards._card = None

    with pytest.raises(AgentCardNotFoundError):
        await harness.catalogue_sync_service.sync(listing.id)


async def test_sync_wholesale_replaces_the_snapshot(harness_factory):
    agent_cards = StubAgentCardsClient(card={
        "name": "Old Name", "description": "old", "skills": [{"id": "a", "name": "A"}], "trust_score": 0.5,
    })
    harness = harness_factory(agent_cards=agent_cards)
    listing = await harness.governance_service.submit(tenant_id="acme", agent_card_id="card-1", submitted_by="alice")

    agent_cards._card = {"name": "New Name", "description": "new", "skills": [{"id": "b", "name": "B"}], "trust_score": 0.9}
    synced = await harness.catalogue_sync_service.sync(listing.id)

    assert synced.name == "New Name"
    assert synced.trust_score_snapshot == 0.9
    assert synced.skills_snapshot == [{"id": "b", "name": "B"}]
