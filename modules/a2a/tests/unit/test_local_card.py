"""Tests for core/local_card.py -- the skills this platform advertises
outbound are exactly the keys of `skill_definition_map`."""
from __future__ import annotations

from a2a_gateway.config import A2AGatewaySettings
from a2a_gateway.core.local_card import build_local_card


def test_build_local_card_advertises_exactly_the_mapped_skills():
    settings = A2AGatewaySettings(skill_definition_map={"summarize": "def-a", "translate": "def-b"})

    card = build_local_card(settings)

    assert {s.id for s in card.skills} == {"summarize", "translate"}
    assert card.name == settings.agent_name
    assert card.url == settings.self_base_url


def test_build_local_card_with_no_mapped_skills_advertises_none():
    settings = A2AGatewaySettings(skill_definition_map={})

    card = build_local_card(settings)

    assert card.skills == []
