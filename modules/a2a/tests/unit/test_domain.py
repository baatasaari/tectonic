"""Tests for core/domain.py -- the tolerant third-party Agent Card parser
and its round trip with card_to_dict (used for this platform's own
published card)."""
from __future__ import annotations

from a2a_gateway.core.domain import AgentCard, AgentSkill, card_to_dict, parse_agent_card


def test_parse_agent_card_pulls_out_only_the_fields_this_module_needs():
    raw = {
        "name": "peer-agent", "description": "does things", "url": "http://peer",
        "skills": [{"id": "summarize", "name": "Summarize", "description": "summarizes text"}],
        "some_other_field_a_real_a2a_card_might_carry": {"nested": True},
    }

    card = parse_agent_card(raw)

    assert card.name == "peer-agent"
    assert card.supports("summarize")
    assert not card.supports("translate")


def test_parse_agent_card_tolerates_missing_optional_fields():
    card = parse_agent_card({})

    assert card.name == ""
    assert card.skills == []


def test_card_to_dict_round_trips_through_parse_agent_card():
    card = AgentCard(name="n", description="d", url="http://u", skills=[AgentSkill(id="s1", name="Skill One")])

    round_tripped = parse_agent_card(card_to_dict(card))

    assert round_tripped == card
