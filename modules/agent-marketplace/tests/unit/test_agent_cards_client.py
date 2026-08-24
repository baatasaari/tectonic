"""Tests for clients/agent_cards_client.py -- calls the real GET
/v1/agent-cards/{id} endpoint shape, including the 404-as-None path."""
from __future__ import annotations

import httpx
import respx

from agent_marketplace.clients.agent_cards_client import HTTPAgentCardsClient


@respx.mock
async def test_get_card_returns_the_card_body():
    respx.get("http://cards.local/v1/agent-cards/card-1").mock(
        return_value=httpx.Response(200, json={"id": "card-1", "name": "Search Agent", "trust_score": 0.8, "skills": []})
    )
    client = HTTPAgentCardsClient("http://cards.local")

    card = await client.get_card("card-1")

    assert card["name"] == "Search Agent"


@respx.mock
async def test_get_card_returns_none_on_404():
    respx.get("http://cards.local/v1/agent-cards/does-not-exist").mock(return_value=httpx.Response(404))
    client = HTTPAgentCardsClient("http://cards.local")

    card = await client.get_card("does-not-exist")

    assert card is None
