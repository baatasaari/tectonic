"""Tests for clients/auditability_client.py -- calls Auditability's
real POST /v1/auditability/events endpoint shape."""
from __future__ import annotations

import httpx
import respx

from secrets_and_credential_management.clients.auditability_client import HTTPAuditabilityClient


@respx.mock
async def test_emit_posts_the_event_body():
    route = respx.post("http://auditability.local/v1/auditability/events").mock(
        return_value=httpx.Response(201, json={
            "id": "e1", "tenant_id": "acme", "source_module": "secrets-and-credential-management",
            "event_type": "secrets.access_denied", "payload": {}, "sequence_number": 1,
            "entry_hash": "abc", "prev_hash": None, "occurred_at": "2026-01-01T00:00:00Z",
        })
    )
    client = HTTPAuditabilityClient("http://auditability.local")

    await client.emit({
        "tenant_id": "acme", "event_type": "secrets.access_denied",
        "payload": {"secret_id": "s1"},
    })

    assert route.called
    sent_body = route.calls.last.request.content.decode()
    assert "access_denied" in sent_body
