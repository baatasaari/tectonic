"""Tests for clients/identity_access_client.py -- calls Identity and
Access's real POST /v1/identity-access/authorize endpoint shape."""
from __future__ import annotations

import httpx
import respx

from secrets_and_credential_management.clients.identity_access_client import (
    HTTPIdentityAccessClient,
)


@respx.mock
async def test_authorize_posts_the_token_and_scope_and_returns_the_decision():
    route = respx.post("http://identity-access.local/v1/identity-access/authorize").mock(
        return_value=httpx.Response(200, json={"allowed": True, "reason": "ok"})
    )
    client = HTTPIdentityAccessClient("http://identity-access.local")

    result = await client.authorize(token="tok", required_scope="secret:acme:db:read")

    assert result == {"allowed": True, "reason": "ok"}
    assert route.called
    sent_body = route.calls.last.request.content.decode()
    assert "secret:acme:db:read" in sent_body
