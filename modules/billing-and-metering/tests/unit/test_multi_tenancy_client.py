"""Tests for clients/multi_tenancy_client.py -- the real
sync_entitlements POST and gate GET request shapes, and both methods'
best-effort/fail-open contracts when Multi-tenancy is unreachable."""
from __future__ import annotations

import httpx
import respx

from billing_and_metering.clients.multi_tenancy_client import HTTPMultiTenancyClient


@respx.mock
async def test_sync_entitlements_posts_the_real_shape():
    route = respx.post("http://multi-tenancy.local/v1/multi-tenancy/tenants/acme/entitlements").mock(
        return_value=httpx.Response(200, json={"tenant_id": "acme", "module_names": ["llm-gateway"], "configured": True}),
    )
    client = HTTPMultiTenancyClient("http://multi-tenancy.local")

    await client.sync_entitlements(tenant_id="acme", module_names=["llm-gateway"])

    assert route.called
    import json
    assert json.loads(route.calls.last.request.content) == {"module_names": ["llm-gateway"]}


@respx.mock
async def test_sync_entitlements_swallows_errors():
    respx.post("http://multi-tenancy.local/v1/multi-tenancy/tenants/acme/entitlements").mock(
        return_value=httpx.Response(500),
    )
    client = HTTPMultiTenancyClient("http://multi-tenancy.local")

    await client.sync_entitlements(tenant_id="acme", module_names=["llm-gateway"])  # must not raise


@respx.mock
async def test_gate_reads_the_real_allowed_reason_shape():
    route = respx.get("http://multi-tenancy.local/v1/multi-tenancy/tenants/acme/gate").mock(
        return_value=httpx.Response(200, json={"allowed": False, "reason": "module not entitled"}),
    )
    client = HTTPMultiTenancyClient("http://multi-tenancy.local")

    allowed, reason = await client.gate(tenant_id="acme", module="llm-gateway")

    assert allowed is False
    assert reason == "module not entitled"
    assert route.calls.last.request.url.params["module"] == "llm-gateway"


@respx.mock
async def test_gate_fails_open_when_multi_tenancy_is_unreachable():
    respx.get("http://multi-tenancy.local/v1/multi-tenancy/tenants/acme/gate").mock(
        return_value=httpx.Response(500),
    )
    client = HTTPMultiTenancyClient("http://multi-tenancy.local")

    allowed, reason = await client.gate(tenant_id="acme", module="llm-gateway")

    assert allowed is True
    assert reason == ""
