"""Tests for clients/auditability_client.py -- calls Auditability's
real GET /v1/auditability/events endpoint shape and reads `total`."""
from __future__ import annotations

from datetime import UTC, datetime

import httpx
import respx

from billing_and_metering.clients.auditability_client import HTTPAuditabilityClient


@respx.mock
async def test_count_events_reads_the_total_field():
    route = respx.get("http://auditability.local/v1/auditability/events").mock(
        return_value=httpx.Response(200, json={"items": [], "total": 42, "limit": 1, "offset": 0})
    )
    client = HTTPAuditabilityClient("http://auditability.local")

    total = await client.count_events(
        tenant_id="acme", source_module="identity-and-access",
        occurred_after=datetime(2026, 3, 1, tzinfo=UTC), occurred_before=datetime(2026, 4, 1, tzinfo=UTC),
    )

    assert total == 42
    assert route.called
    params = route.calls.last.request.url.params
    assert params["tenant_id"] == "acme"
    assert params["source_module"] == "identity-and-access"
    assert params["limit"] == "1"
