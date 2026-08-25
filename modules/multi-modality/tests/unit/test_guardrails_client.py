"""Tests for clients/guardrails_client.py -- calls the real
POST /v1/guardrails/check endpoint shape at stage=output."""
from __future__ import annotations

import httpx
import respx

from multi_modality.clients.guardrails_client import HTTPGuardrailsClient


@respx.mock
async def test_check_groundedness_posts_the_output_stage_check():
    route = respx.post("http://guardrails.local/v1/guardrails/check").mock(
        return_value=httpx.Response(200, json={
            "decision": "allow", "violation_category": None, "redacted_text": None, "checks_run": ["groundedness_check"],
        })
    )
    client = HTTPGuardrailsClient("http://guardrails.local")

    result = await client.check_groundedness(tenant_id="acme", text="extracted content", context="reference text")

    assert result["decision"] == "allow"
    sent = route.calls.last.request
    body = sent.content.decode()
    assert '"stage":"output"' in body.replace(" ", "")
    assert sent.headers["X-Tenant-Id"] == "acme"


@respx.mock
async def test_check_groundedness_returns_a_block_decision():
    respx.post("http://guardrails.local/v1/guardrails/check").mock(
        return_value=httpx.Response(200, json={
            "decision": "block", "violation_category": "ungrounded", "redacted_text": None, "checks_run": ["groundedness_check"],
        })
    )
    client = HTTPGuardrailsClient("http://guardrails.local")

    result = await client.check_groundedness(tenant_id="acme", text="hallucinated content", context="reference text")

    assert result["decision"] == "block"
    assert result["violation_category"] == "ungrounded"
