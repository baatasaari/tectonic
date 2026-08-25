"""API-level tests for the FastAPI routes -- role/identity creation, the
revoke -> reinstate lifecycle, token issuance, and the zero-trust
authorize gate through a real app.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from identity_and_access.api.deps import get_ctx, get_repository
from identity_and_access.api.routes_identity_and_access import router
from identity_and_access.app_context import AppContext
from identity_and_access.config import IdentityAndAccessSettings
from identity_and_access.core.fakes import InMemoryIdentityAccessRepository, StubAuditabilityClient
from identity_and_access.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)
from identity_and_access.security.token_signer import JWTTokenSigner

SECRET = INSECURE_DEFAULT_SECRET
SIGNING_SECRET = "test-token-signing-secret-at-least-32-bytes-long"


def _app(repository, *, auditability=None):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="identity-access", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=IdentityAndAccessSettings(), engine=None, session_factory=None,
        auditability=auditability or StubAuditabilityClient(), signer=JWTTokenSigner(signing_secret=SIGNING_SECRET),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="conversational-engine", audience="identity-access", shared_secret=SECRET)


def _headers(**extra):
    return {"Authorization": f"Bearer {_token()}", **extra}


def test_create_role_and_register_identity():
    app = _app(InMemoryIdentityAccessRepository())

    with TestClient(app) as client:
        role = client.post(
            "/v1/identity-access/roles", json={"name": "reader", "scopes": ["cards:read"]}, headers=_headers(),
        ).json()
        assert role["scopes"] == ["cards:read"]

        identity = client.post(
            "/v1/identity-access/identities",
            json={"name": "agent-1", "type": "agent", "role_names": ["reader"]},
            headers=_headers(**{"X-Tenant-Id": "acme"}),
        ).json()

    assert identity["tenant_id"] == "acme"
    assert identity["status"] == "active"
    assert identity["role_names"] == ["reader"]


def test_register_without_a_bearer_token_is_rejected():
    app = _app(InMemoryIdentityAccessRepository())

    with TestClient(app) as client:
        resp = client.post("/v1/identity-access/identities", json={"name": "agent-1"})

    assert resp.status_code == 401


def test_register_with_an_unknown_role_returns_404():
    app = _app(InMemoryIdentityAccessRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/identity-access/identities", json={"name": "agent-1", "role_names": ["does-not-exist"]},
            headers=_headers(),
        )

    assert resp.status_code == 404


def test_full_issue_token_authorize_flow():
    app = _app(InMemoryIdentityAccessRepository())
    headers = _headers(**{"X-Tenant-Id": "acme"})

    with TestClient(app) as client:
        client.post("/v1/identity-access/roles", json={"name": "reader", "scopes": ["cards:read"]}, headers=headers)
        identity = client.post(
            "/v1/identity-access/identities", json={"name": "agent-1", "role_names": ["reader"]}, headers=headers,
        ).json()

        issued = client.post(
            "/v1/identity-access/tokens", json={"identity_id": identity["id"]}, headers=headers,
        ).json()
        assert issued["granted_scopes"] == ["cards:read"]

        allowed = client.post(
            "/v1/identity-access/authorize",
            json={"token": issued["token"], "required_scope": "cards:read"}, headers=headers,
        ).json()
        assert allowed["allowed"] is True

        denied = client.post(
            "/v1/identity-access/authorize",
            json={"token": issued["token"], "required_scope": "cards:delete"}, headers=headers,
        ).json()
        assert denied["allowed"] is False


def test_revoking_an_identity_stops_its_outstanding_token_immediately():
    app = _app(InMemoryIdentityAccessRepository())
    headers = _headers()

    with TestClient(app) as client:
        client.post("/v1/identity-access/roles", json={"name": "reader", "scopes": ["cards:read"]}, headers=headers)
        identity = client.post(
            "/v1/identity-access/identities", json={"name": "agent-1", "role_names": ["reader"]}, headers=headers,
        ).json()
        issued = client.post(
            "/v1/identity-access/tokens", json={"identity_id": identity["id"]}, headers=headers,
        ).json()

        client.post(f"/v1/identity-access/identities/{identity['id']}/revoke", headers=headers)

        resp = client.post(
            "/v1/identity-access/authorize",
            json={"token": issued["token"], "required_scope": "cards:read"}, headers=headers,
        )

    assert resp.json()["allowed"] is False


def test_issue_token_for_a_revoked_identity_returns_403():
    app = _app(InMemoryIdentityAccessRepository())
    headers = _headers()

    with TestClient(app) as client:
        identity = client.post("/v1/identity-access/identities", json={"name": "agent-1"}, headers=headers).json()
        client.post(f"/v1/identity-access/identities/{identity['id']}/revoke", headers=headers)

        resp = client.post("/v1/identity-access/tokens", json={"identity_id": identity["id"]}, headers=headers)

    assert resp.status_code == 403


def test_get_identity_returns_404_when_missing():
    app = _app(InMemoryIdentityAccessRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/identity-access/identities/does-not-exist", headers=_headers())

    assert resp.status_code == 404


def test_list_auth_decisions_for_an_identity():
    app = _app(InMemoryIdentityAccessRepository())
    headers = _headers()

    with TestClient(app) as client:
        identity = client.post("/v1/identity-access/identities", json={"name": "agent-1"}, headers=headers).json()
        issued = client.post(
            "/v1/identity-access/tokens", json={"identity_id": identity["id"]}, headers=headers,
        ).json()
        client.post(
            "/v1/identity-access/authorize",
            json={"token": issued["token"], "required_scope": "cards:read"}, headers=headers,
        )

        resp = client.get(f"/v1/identity-access/identities/{identity['id']}/auth-decisions", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["total"] == 1
