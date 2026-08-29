"""API-level tests for SCIM 2.0 endpoints (api/routes_scim.py) --
authenticated by the per-tenant SCIM bearer token, not the platform's
own service JWT."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from identity_and_access.api.deps import get_ctx, get_repository
from identity_and_access.api.routes_scim import router
from identity_and_access.app_context import AppContext
from identity_and_access.config import IdentityAndAccessSettings
from identity_and_access.core.fakes import (
    InMemoryIdentityAccessRepository,
    StubAuditabilityClient,
    StubOidcTokenVerifier,
    StubSamlAssertionVerifier,
)
from identity_and_access.core.scim_token_service import ScimTokenService
from identity_and_access.security.token_signer import JWTTokenSigner

SIGNING_SECRET = "test-token-signing-secret-at-least-32-bytes-long"


def _app(repository):
    app = FastAPI()
    app.include_router(router)

    ctx = AppContext(
        settings=IdentityAndAccessSettings(), engine=None, session_factory=None,
        auditability=StubAuditabilityClient(), signer=JWTTokenSigner(signing_secret=SIGNING_SECRET),
        oidc_verifier=StubOidcTokenVerifier(), saml_verifier=StubSamlAssertionVerifier(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


async def _issue_token(repository, tenant_id="acme") -> str:
    _, cleartext = await ScimTokenService(repository).create(tenant_id=tenant_id, name="Okta SCIM")
    return cleartext


def test_create_user_without_a_token_is_rejected():
    app = _app(InMemoryIdentityAccessRepository())
    with TestClient(app) as client:
        resp = client.post("/scim/v2/acme/Users", json={"userName": "alice@acme.com"})

    assert resp.status_code == 401


async def test_create_user_with_a_valid_token_succeeds():
    repository = InMemoryIdentityAccessRepository()
    token = await _issue_token(repository)
    app = _app(repository)

    with TestClient(app) as client:
        resp = client.post(
            "/scim/v2/acme/Users", json={"userName": "alice@acme.com", "displayName": "Alice"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["userName"] == "alice@acme.com"
    assert body["active"] is True
    assert body["schemas"] == ["urn:ietf:params:scim:schemas:core:2.0:User"]


async def test_a_token_minted_for_a_different_tenant_is_rejected():
    repository = InMemoryIdentityAccessRepository()
    token = await _issue_token(repository, tenant_id="globex")
    app = _app(repository)

    with TestClient(app) as client:
        resp = client.post(
            "/scim/v2/acme/Users", json={"userName": "alice@acme.com"}, headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 401


async def test_list_users_supports_the_username_filter():
    repository = InMemoryIdentityAccessRepository()
    token = await _issue_token(repository)
    app = _app(repository)
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        client.post("/scim/v2/acme/Users", json={"userName": "alice@acme.com"}, headers=headers)
        client.post("/scim/v2/acme/Users", json={"userName": "bob@acme.com"}, headers=headers)

        resp = client.get("/scim/v2/acme/Users", params={"filter": 'userName eq "alice@acme.com"'}, headers=headers)

    body = resp.json()
    assert body["totalResults"] == 1
    assert body["Resources"][0]["userName"] == "alice@acme.com"


async def test_patch_active_false_deactivates_the_user():
    repository = InMemoryIdentityAccessRepository()
    token = await _issue_token(repository)
    app = _app(repository)
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        created = client.post("/scim/v2/acme/Users", json={"userName": "alice@acme.com"}, headers=headers).json()

        resp = client.patch(
            f"/scim/v2/acme/Users/{created['id']}",
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [{"op": "replace", "path": "active", "value": False}],
            },
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["active"] is False


async def test_delete_user_deactivates_rather_than_404ing_afterward():
    repository = InMemoryIdentityAccessRepository()
    token = await _issue_token(repository)
    app = _app(repository)
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        created = client.post("/scim/v2/acme/Users", json={"userName": "alice@acme.com"}, headers=headers).json()

        delete_resp = client.delete(f"/scim/v2/acme/Users/{created['id']}", headers=headers)
        get_resp = client.get(f"/scim/v2/acme/Users/{created['id']}", headers=headers)

    assert delete_resp.status_code == 204
    assert get_resp.status_code == 200
    assert get_resp.json()["active"] is False


async def test_create_group_and_patch_add_member():
    repository = InMemoryIdentityAccessRepository()
    token = await _issue_token(repository)
    app = _app(repository)
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        user = client.post("/scim/v2/acme/Users", json={"userName": "alice@acme.com"}, headers=headers).json()
        group = client.post("/scim/v2/acme/Groups", json={"displayName": "Engineers"}, headers=headers).json()

        resp = client.patch(
            f"/scim/v2/acme/Groups/{group['id']}",
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [{"op": "add", "path": "members", "value": [{"value": user["id"]}]}],
            },
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["members"] == [{"value": user["id"], "display": ""}]
