"""Tests for clients/multi_tenancy_client.py -- the real quota/check
POST request shape (including the capacity-shaped `current_usage` this
module supplies), and its best-effort/fail-open contract when
Multi-tenancy is unreachable (the same pattern LLM Gateway's and Billing
and Metering's own HTTPMultiTenancyClient already established)."""
from __future__ import annotations

import json

import httpx
import respx

from vector_db.clients.multi_tenancy_client import HTTPMultiTenancyClient


@respx.mock
async def test_check_quota_posts_the_real_shape_including_current_usage():
    route = respx.post("http://multi-tenancy.local/v1/multi-tenancy/tenants/acme/quota/check").mock(
        return_value=httpx.Response(
            200,
            json={
                "allowed": True, "resource_class": "vector_count", "limit": 100000.0, "used": 42.0,
                "remaining": 99958.0, "reason": "active",
            },
        ),
    )
    client = HTTPMultiTenancyClient("http://multi-tenancy.local")

    allowed, reason = await client.check_quota(tenant_id="acme", resource_class="vector_count", current_usage=41.0)

    assert allowed is True
    assert reason == "active"
    assert route.called
    assert json.loads(route.calls.last.request.content) == {
        "resource_class": "vector_count", "amount": 1.0, "current_usage": 41.0,
    }


@respx.mock
async def test_check_quota_reads_a_real_denial():
    respx.post("http://multi-tenancy.local/v1/multi-tenancy/tenants/acme/quota/check").mock(
        return_value=httpx.Response(
            200,
            json={
                "allowed": False, "resource_class": "vector_count", "limit": 100.0, "used": 100.0,
                "remaining": 0.0, "reason": "quota exceeded for vector_count",
            },
        ),
    )
    client = HTTPMultiTenancyClient("http://multi-tenancy.local")

    allowed, reason = await client.check_quota(tenant_id="acme", resource_class="vector_count", current_usage=100.0)

    assert allowed is False
    assert reason == "quota exceeded for vector_count"


@respx.mock
async def test_check_quota_fails_open_when_multi_tenancy_is_unreachable():
    respx.post("http://multi-tenancy.local/v1/multi-tenancy/tenants/acme/quota/check").mock(
        return_value=httpx.Response(500),
    )
    client = HTTPMultiTenancyClient("http://multi-tenancy.local")

    allowed, reason = await client.check_quota(tenant_id="acme", resource_class="vector_count", current_usage=1.0)

    assert allowed is True
    assert reason == ""
