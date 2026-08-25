"""Tests for clients/identity_access_client.py -- calls Identity and
Access's real identity/token endpoint shapes."""
from __future__ import annotations

import httpx
import respx

from sdk_and_developer_portal.clients.identity_access_client import HTTPIdentityAccessClient


@respx.mock
async def test_register_identity_returns_the_new_id():
    respx.post("http://identity-access.local/v1/identity-access/identities").mock(
        return_value=httpx.Response(201, json={
            "id": "i1", "tenant_id": "default", "name": "Ada", "type": "user", "status": "active",
            "role_names": [], "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
        })
    )
    client = HTTPIdentityAccessClient("http://identity-access.local")

    identity_id = await client.register_identity(name="Ada", type_="user", role_names=[])

    assert identity_id == "i1"


@respx.mock
async def test_revoke_identity_posts_to_the_real_revoke_endpoint():
    route = respx.post("http://identity-access.local/v1/identity-access/identities/i1/revoke").mock(
        return_value=httpx.Response(200, json={
            "id": "i1", "tenant_id": "default", "name": "Ada", "type": "user", "status": "revoked",
            "role_names": [], "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
        })
    )
    client = HTTPIdentityAccessClient("http://identity-access.local")

    await client.revoke_identity("i1")

    assert route.called


@respx.mock
async def test_issue_token_returns_the_token_shape():
    respx.post("http://identity-access.local/v1/identity-access/tokens").mock(
        return_value=httpx.Response(201, json={"token": "jwt-here", "granted_scopes": ["cards:read"]})
    )
    client = HTTPIdentityAccessClient("http://identity-access.local")

    issued = await client.issue_token(identity_id="i1", requested_scopes=["cards:read"])

    assert issued == {"token": "jwt-here", "granted_scopes": ["cards:read"]}
