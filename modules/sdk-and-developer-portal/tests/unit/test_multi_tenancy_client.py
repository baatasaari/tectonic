"""Tests for clients/multi_tenancy_client.py -- calls Multi-tenancy's
real POST /v1/multi-tenancy/tenants endpoint shape."""
from __future__ import annotations

import httpx
import respx

from sdk_and_developer_portal.clients.multi_tenancy_client import HTTPMultiTenancyClient


@respx.mock
async def test_create_tenant_returns_the_new_id_and_sends_the_sandbox_tier():
    route = respx.post("http://multi-tenancy.local/v1/multi-tenancy/tenants").mock(
        return_value=httpx.Response(201, json={
            "id": "t1", "name": "sandbox-Ada", "status": "active", "tier": "sandbox",
            "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
        })
    )
    client = HTTPMultiTenancyClient("http://multi-tenancy.local")

    tenant_id = await client.create_tenant(name="sandbox-Ada", tier="sandbox")

    assert tenant_id == "t1"
    sent_body = route.calls.last.request.content.decode()
    assert '"tier":"sandbox"' in sent_body
