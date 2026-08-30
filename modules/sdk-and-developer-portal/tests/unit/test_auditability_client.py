"""Tests for clients/auditability_client.py -- count_events reads
`total`, get_event_occurred_at reads a targeted offset's `occurred_at`."""
from __future__ import annotations

import httpx
import respx

from sdk_and_developer_portal.clients.auditability_client import HTTPAuditabilityClient


@respx.mock
async def test_count_events_reads_the_total_field():
    respx.get("http://auditability.local/v1/auditability/events").mock(
        return_value=httpx.Response(200, json={"items": [], "total": 7, "limit": 1, "offset": 0})
    )
    client = HTTPAuditabilityClient("http://auditability.local")

    total = await client.count_events(tenant_id="acme")

    assert total == 7


@respx.mock
async def test_get_event_occurred_at_reads_the_targeted_offset():
    route = respx.get("http://auditability.local/v1/auditability/events").mock(
        return_value=httpx.Response(200, json={
            "items": [{
                "id": "e1", "tenant_id": "acme", "source_module": "secrets-and-credential-management",
                "event_type": "secrets.access_attempt", "payload": {}, "sequence_number": 1,
                "entry_hash": "abc", "prev_hash": None, "occurred_at": "2026-03-01T12:00:00+00:00",
            }],
            "total": 5, "limit": 1, "offset": 4,
        })
    )
    client = HTTPAuditabilityClient("http://auditability.local")

    occurred_at = await client.get_event_occurred_at(tenant_id="acme", offset=4)

    assert occurred_at.isoformat() == "2026-03-01T12:00:00+00:00"
    assert route.calls.last.request.url.params["offset"] == "4"
