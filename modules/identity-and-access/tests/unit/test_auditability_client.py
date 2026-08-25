"""Tests for clients/auditability_client.py -- calls Auditability's
real POST /v1/auditability/events endpoint shape."""
from __future__ import annotations

import httpx
import respx

from identity_and_access.clients.auditability_client import HTTPAuditabilityClient


@respx.mock
async def test_emit_posts_the_event_body():
    route = respx.post("http://auditability.local/v1/auditability/events").mock(
        return_value=httpx.Response(201, json={
            "id": "e1", "tenant_id": "acme", "source_module": "identity-access",
            "event_type": "identity_access.unauthorized_attempt", "payload": {}, "sequence_number": 1,
            "entry_hash": "abc", "prev_hash": None, "occurred_at": "2026-01-01T00:00:00Z",
        })
    )
    client = HTTPAuditabilityClient("http://auditability.local")

    await client.emit({
        "tenant_id": "acme", "event_type": "identity_access.unauthorized_attempt",
        "payload": {"identity_id": "i1"},
    })

    assert route.called
    sent_body = route.calls.last.request.content.decode()
    assert "unauthorized_attempt" in sent_body
