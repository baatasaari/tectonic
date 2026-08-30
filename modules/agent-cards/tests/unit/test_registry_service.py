"""Tests for core/registry_service.py -- card CRUD."""
from __future__ import annotations

import pytest

from agent_cards.core.domain import AgentCardNotFoundError, AgentSkill


async def test_register_creates_a_card(harness):
    card = await harness.registry_service.register(
        tenant_id="acme", agent_ref="search-agent", name="Search Agent", description="Finds things",
        url="http://search-agent.example", skills=[AgentSkill(id="search", name="Search")],
    )

    assert card.tenant_id == "acme"
    assert card.agent_ref == "search-agent"
    assert card.trust_score is None


async def test_get_raises_for_an_unknown_card(harness):
    with pytest.raises(AgentCardNotFoundError):
        await harness.registry_service.get("does-not-exist")


async def test_update_bumps_last_verified_at_and_changes_fields(harness):
    card = await harness.registry_service.register(
        tenant_id="acme", agent_ref="a1", name="Old Name", description="", url="http://a", skills=[],
    )
    before = card.last_verified_at

    updated = await harness.registry_service.update(card.id, name="New Name")

    assert updated.name == "New Name"
    assert updated.last_verified_at >= before


async def test_list_filters_by_tenant(harness):
    await harness.registry_service.register(tenant_id="acme", agent_ref="a1", name="a", description="", url="http://a", skills=[])
    await harness.registry_service.register(tenant_id="globex", agent_ref="a2", name="b", description="", url="http://b", skills=[])

    cards, total = await harness.registry_service.list(tenant_id="acme")

    assert total == 1
    assert cards[0].tenant_id == "acme"


async def test_list_paginates(harness):
    for i in range(5):
        await harness.registry_service.register(
            tenant_id="acme", agent_ref=f"a{i}", name=f"a{i}", description="", url=f"http://{i}", skills=[],
        )

    page1, total1 = await harness.registry_service.list(limit=2, offset=0)
    page2, total2 = await harness.registry_service.list(limit=2, offset=2)

    assert total1 == total2 == 5
    assert len(page1) == 2
    assert len(page2) == 2
    assert {c.id for c in page1}.isdisjoint({c.id for c in page2})
