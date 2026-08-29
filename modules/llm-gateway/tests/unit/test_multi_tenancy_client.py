"""Tests for clients/multi_tenancy_client.py -- the real quota/check
POST request shape, and its best-effort/fail-open contract when
Multi-tenancy is unreachable (the same pattern Billing and Metering's
own HTTPMultiTenancyClient.gate already established)."""
from __future__ import annotations

import json

import httpx
import respx

from llm_gateway.clients.multi_tenancy_client import HTTPMultiTenancyClient


@respx.mock
async def test_check_quota_posts_the_real_shape_and_reads_allowed():
    route = respx.post("http://multi-tenancy.local/v1/multi-tenancy/tenants/acme/quota/check").mock(
        return_value=httpx.Response(
            200,
            json={
                "allowed": True, "resource_class": "requests_per_minute", "limit": 600.0, "used": 5.0,
                "remaining": 595.0, "reason": "active",
            },
        ),
    )
    client = HTTPMultiTenancyClient("http://multi-tenancy.local")

    allowed, reason = await client.check_quota(tenant_id="acme", resource_class="requests_per_minute")

    assert allowed is True
    assert reason == "active"
    assert route.called
    assert json.loads(route.calls.last.request.content) == {"resource_class": "requests_per_minute", "amount": 1.0}


@respx.mock
async def test_check_quota_reads_a_real_denial():
    respx.post("http://multi-tenancy.local/v1/multi-tenancy/tenants/acme/quota/check").mock(
        return_value=httpx.Response(
            200,
            json={
                "allowed": False, "resource_class": "requests_per_minute", "limit": 600.0, "used": 600.0,
                "remaining": 0.0, "reason": "quota exceeded for requests_per_minute",
            },
        ),
    )
    client = HTTPMultiTenancyClient("http://multi-tenancy.local")

    allowed, reason = await client.check_quota(tenant_id="acme", resource_class="requests_per_minute")

    assert allowed is False
    assert reason == "quota exceeded for requests_per_minute"


@respx.mock
async def test_check_quota_fails_open_when_multi_tenancy_is_unreachable():
    respx.post("http://multi-tenancy.local/v1/multi-tenancy/tenants/acme/quota/check").mock(
        return_value=httpx.Response(500),
    )
    client = HTTPMultiTenancyClient("http://multi-tenancy.local")

    allowed, reason = await client.check_quota(tenant_id="acme", resource_class="requests_per_minute")

    assert allowed is True
    assert reason == ""
