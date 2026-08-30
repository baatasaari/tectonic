"""Tests for clients/evaluation_framework_client.py -- calls the real
GET /v1/evaluation-framework/scores endpoint shape."""
from __future__ import annotations

import httpx
import respx

from agent_cards.clients.evaluation_framework_client import HTTPEvaluationFrameworkClient


@respx.mock
async def test_list_scores_returns_the_items_array():
    route = respx.get("http://evalfw.local/v1/evaluation-framework/scores").mock(
        return_value=httpx.Response(200, json={
            "items": [{"id": "s1", "metric_name": "faithfulness", "score": 0.9, "threshold": 0.8, "passed": True, "created_at": "2026-01-01T00:00:00Z"}],
            "total": 1, "limit": 200, "offset": 0,
        })
    )
    client = HTTPEvaluationFrameworkClient("http://evalfw.local")

    scores = await client.list_scores(tenant_id="acme", agent_ref="agent-1")

    assert len(scores) == 1
    assert scores[0]["metric_name"] == "faithfulness"
    sent = route.calls.last.request
    assert "tenant_id=acme" in str(sent.url)
    assert "agent_ref=agent-1" in str(sent.url)


@respx.mock
async def test_list_scores_returns_empty_list_when_the_agent_has_no_history():
    respx.get("http://evalfw.local/v1/evaluation-framework/scores").mock(
        return_value=httpx.Response(200, json={"items": [], "total": 0, "limit": 200, "offset": 0})
    )
    client = HTTPEvaluationFrameworkClient("http://evalfw.local")

    scores = await client.list_scores(tenant_id="acme", agent_ref="agent-1")

    assert scores == []
