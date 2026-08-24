"""Tests for core/discovery_service.py -- search + staleness computation."""
from __future__ import annotations

from datetime import timedelta

from agent_cards.core.domain import AgentSkill, now


async def test_search_ranks_by_trust_score_descending(harness_factory):
    harness = harness_factory()
    low = await harness.registry_service.register(tenant_id="acme", agent_ref="low", name="low", description="", url="http://a", skills=[])
    high = await harness.registry_service.register(tenant_id="acme", agent_ref="high", name="high", description="", url="http://b", skills=[])
    low.trust_score = 0.2
    high.trust_score = 0.9
    await harness.repository.update_card(low)
    await harness.repository.update_card(high)

    results, total = await harness.discovery_service.search(tenant_id="acme")

    assert total == 2
    assert [card.id for card, _ in results] == [high.id, low.id]


async def test_search_sorts_unscored_cards_after_scored_ones(harness):
    scored = await harness.registry_service.register(tenant_id="acme", agent_ref="s", name="s", description="", url="http://a", skills=[])
    scored.trust_score = 0.1
    await harness.repository.update_card(scored)
    unscored = await harness.registry_service.register(tenant_id="acme", agent_ref="u", name="u", description="", url="http://b", skills=[])

    results, _ = await harness.discovery_service.search(tenant_id="acme")

    assert [card.id for card, _ in results] == [scored.id, unscored.id]


async def test_search_filters_by_skill_id(harness):
    await harness.registry_service.register(
        tenant_id="acme", agent_ref="a1", name="a", description="", url="http://a", skills=[AgentSkill(id="search", name="Search")],
    )
    await harness.registry_service.register(
        tenant_id="acme", agent_ref="a2", name="b", description="", url="http://b", skills=[AgentSkill(id="translate", name="Translate")],
    )

    results, total = await harness.discovery_service.search(tenant_id="acme", skill_id="search")

    assert total == 1
    assert results[0][0].agent_ref == "a1"


async def test_search_marks_a_card_as_stale_past_the_ttl(harness_factory):
    harness = harness_factory(staleness_ttl_seconds=60)
    card = await harness.registry_service.register(tenant_id="acme", agent_ref="a1", name="a", description="", url="http://a", skills=[])
    card.last_verified_at = now() - timedelta(seconds=120)
    await harness.repository.update_card(card)

    results, _ = await harness.discovery_service.search(tenant_id="acme")

    assert results[0][1] is True  # is_stale


async def test_search_does_not_mark_a_fresh_card_as_stale(harness_factory):
    harness = harness_factory(staleness_ttl_seconds=3600)
    await harness.registry_service.register(tenant_id="acme", agent_ref="a1", name="a", description="", url="http://a", skills=[])

    results, _ = await harness.discovery_service.search(tenant_id="acme")

    assert results[0][1] is False
