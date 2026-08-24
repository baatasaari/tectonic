"""Tests for clients/regulatory_compliance_client.py -- calls the real
GET /v1/regulatory-compliance/coverage endpoint shape."""
from __future__ import annotations

import httpx
import respx

from agent_cards.clients.regulatory_compliance_client import HTTPRegulatoryComplianceClient


@respx.mock
async def test_coverage_returns_the_coverage_percentage():
    route = respx.get("http://regcomp.local/v1/regulatory-compliance/coverage").mock(
        return_value=httpx.Response(200, json={
            "tenant_id": "acme", "framework_name": "eu_ai_act", "coverage_percentage": 75.0, "gaps": ["human_oversight"],
        })
    )
    client = HTTPRegulatoryComplianceClient("http://regcomp.local")

    coverage = await client.coverage(tenant_id="acme", framework_name="eu_ai_act")

    assert coverage == 75.0
    sent = route.calls.last.request
    assert "framework_name=eu_ai_act" in str(sent.url)
