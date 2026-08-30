"""Tests for clients/module_spec_client.py -- fetches a peer's real
GET /openapi.json with a scoped bearer token."""
from __future__ import annotations

import httpx
import respx

from sdk_and_developer_portal.clients.module_spec_client import HTTPModuleSpecClient
from sdk_and_developer_portal.security.jwt_auth import verify_service_token


@respx.mock
async def test_fetch_spec_returns_the_parsed_spec_and_sends_a_scoped_token():
    route = respx.get("http://auditability.local/openapi.json").mock(
        return_value=httpx.Response(200, json={"info": {"title": "Auditability"}, "paths": {}})
    )
    client = HTTPModuleSpecClient(issuer="sdk-and-developer-portal", shared_secret="test-shared-secret-at-least-32-bytes-long")

    spec = await client.fetch_spec(base_url="http://auditability.local", audience="auditability")

    assert spec["info"]["title"] == "Auditability"
    sent_header = route.calls.last.request.headers["authorization"]
    token = sent_header.removeprefix("Bearer ")
    claims = verify_service_token(token, audience="auditability", shared_secret="test-shared-secret-at-least-32-bytes-long")
    assert claims["iss"] == "sdk-and-developer-portal"
