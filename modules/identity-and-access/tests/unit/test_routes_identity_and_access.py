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
from identity_and_access.core.fakes import (
    InMemoryIdentityAccessRepository,
    StubAuditabilityClient,
    StubOidcTokenVerifier,
    StubSamlAssertionVerifier,
)
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
        oidc_verifier=StubOidcTokenVerifier(), saml_verifier=StubSamlAssertionVerifier(),
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
    headers = _headers(**{"X-Tenant-Id": "acme"})

    with TestClient(app) as client:
        role = client.post(
            "/v1/identity-access/roles", json={"name": "reader", "scopes": ["cards:read"]}, headers=headers,
        ).json()
        assert role["scopes"] == ["cards:read"]
        assert role["tenant_id"] == "acme"

        identity = client.post(
            "/v1/identity-access/identities",
            json={"name": "agent-1", "type": "agent", "role_names": ["reader"]},
            headers=headers,
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


def test_list_identities_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    """Ticket #82: a raw `Query()` string never runs through a Pydantic
    body field's own NUL-byte validator, so this reached the repository
    (and, against real Postgres, the database itself) raw instead of a
    clean 422."""
    app = _app(InMemoryIdentityAccessRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/identity-access/identities", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_list_identities_rejects_a_status_that_is_not_a_real_identity_status():
    """`status` used to be a bare `str` hand-converted to `IdentityStatus`,
    raising an unhandled `ValueError` (500) for any non-member string --
    now typed `IdentityStatus` directly so FastAPI/Pydantic rejects it
    with a clean 422."""
    app = _app(InMemoryIdentityAccessRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/identity-access/identities", params={"status": "not-a-real-status"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_list_identity_providers_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    app = _app(InMemoryIdentityAccessRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/identity-access/identity-providers", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_list_groups_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    app = _app(InMemoryIdentityAccessRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/identity-access/groups", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_list_scim_tokens_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    app = _app(InMemoryIdentityAccessRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/identity-access/scim-tokens", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_list_roles_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    app = _app(InMemoryIdentityAccessRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/identity-access/roles", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_creating_the_same_role_name_twice_for_one_tenant_returns_409():
    app = _app(InMemoryIdentityAccessRepository())
    headers = _headers(**{"X-Tenant-Id": "acme"})

    with TestClient(app) as client:
        client.post("/v1/identity-access/roles", json={"name": "reader", "scopes": ["cards:read"]}, headers=headers)
        resp = client.post(
            "/v1/identity-access/roles", json={"name": "reader", "scopes": ["cards:read"]}, headers=headers,
        )

    assert resp.status_code == 409


def test_two_tenants_can_each_create_a_role_with_the_same_name():
    """IAM v2 foundation: this used to fail outright -- `roles.name` was the
    sole, platform-global primary key, so a second tenant could never
    create a role with a name any other tenant already used."""
    app = _app(InMemoryIdentityAccessRepository())

    with TestClient(app) as client:
        acme = client.post(
            "/v1/identity-access/roles", json={"name": "admin", "scopes": ["cards:admin"]},
            headers=_headers(**{"X-Tenant-Id": "acme"}),
        )
        globex = client.post(
            "/v1/identity-access/roles", json={"name": "admin", "scopes": ["cards:read"]},
            headers=_headers(**{"X-Tenant-Id": "globex"}),
        )

    assert acme.status_code == 201
    assert globex.status_code == 201
    assert acme.json()["id"] != globex.json()["id"]


def test_grant_and_revoke_a_role_on_an_already_registered_identity():
    """The other IAM v2 foundation gap this fixes: before this, a role
    could only ever be set once, at registration -- there was no way to
    grant or revoke a single role on an existing identity at all."""
    app = _app(InMemoryIdentityAccessRepository())
    headers = _headers(**{"X-Tenant-Id": "acme"})

    with TestClient(app) as client:
        client.post("/v1/identity-access/roles", json={"name": "reader", "scopes": ["cards:read"]}, headers=headers)
        identity = client.post(
            "/v1/identity-access/identities", json={"name": "agent-1"}, headers=headers,
        ).json()
        assert identity["role_names"] == []

        granted = client.post(
            f"/v1/identity-access/identities/{identity['id']}/roles",
            json={"role_name": "reader", "granted_by": "operator-1"}, headers=headers,
        )
        assert granted.status_code == 201
        assert granted.json()["role_names"] == ["reader"]

        bindings = client.get(
            f"/v1/identity-access/identities/{identity['id']}/role-bindings", headers=headers,
        ).json()
        assert bindings["total"] == 1
        assert bindings["items"][0]["granted_by"] == "operator-1"
        assert bindings["items"][0]["revoked_at"] is None

        revoked = client.post(
            f"/v1/identity-access/identities/{identity['id']}/roles/reader/revoke", headers=headers,
        )
        assert revoked.status_code == 200
        assert revoked.json()["role_names"] == []

        bindings_after = client.get(
            f"/v1/identity-access/identities/{identity['id']}/role-bindings", headers=headers,
        ).json()
        assert bindings_after["total"] == 1  # same row, updated in place -- not a second row
        assert bindings_after["items"][0]["revoked_at"] is not None


def test_granting_an_unknown_role_returns_404():
    app = _app(InMemoryIdentityAccessRepository())
    headers = _headers()

    with TestClient(app) as client:
        identity = client.post("/v1/identity-access/identities", json={"name": "agent-1"}, headers=headers).json()
        resp = client.post(
            f"/v1/identity-access/identities/{identity['id']}/roles",
            json={"role_name": "does-not-exist"}, headers=headers,
        )

    assert resp.status_code == 404


def test_revoking_a_role_the_identity_does_not_hold_returns_404():
    app = _app(InMemoryIdentityAccessRepository())
    headers = _headers()

    with TestClient(app) as client:
        identity = client.post("/v1/identity-access/identities", json={"name": "agent-1"}, headers=headers).json()
        resp = client.post(
            f"/v1/identity-access/identities/{identity['id']}/roles/never-granted/revoke", headers=headers,
        )

    assert resp.status_code == 404


# Regression tests for the three bug classes this module's own brand-new OpenAPI
# contract-test tier found on its very first run (tests/contract/), fixed
# alongside that tier's rollout -- see schemas/identity_and_access.py's own
# `_reject_null_byte` docstring and db/repository.py's own `_is_valid_uuid`
# docstring for the full reasoning behind each.


def test_creating_a_role_with_a_null_byte_in_the_name_returns_a_clean_422():
    app = _app(InMemoryIdentityAccessRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/identity-access/roles", json={"name": "a\x00b", "scopes": []}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_registering_an_identity_with_a_null_byte_in_the_name_returns_a_clean_422():
    app = _app(InMemoryIdentityAccessRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/identity-access/identities", json={"name": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_registering_an_identity_with_an_invalid_type_returns_a_clean_422():
    """`type` used to be a bare `str` hand-converted to `IdentityType` at the
    route, raising an unhandled `ValueError`/500 for any non-member string --
    now typed `IdentityType` directly so FastAPI/Pydantic itself rejects an
    invalid value with a clean 422."""
    app = _app(InMemoryIdentityAccessRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/identity-access/identities", json={"name": "agent-1", "type": "not-a-real-type"},
            headers=_headers(),
        )

    assert resp.status_code == 422


def test_registering_an_identity_provider_with_an_invalid_provider_type_returns_a_clean_422():
    app = _app(InMemoryIdentityAccessRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/identity-access/identity-providers",
            json={"name": "okta", "provider_type": "not-a-real-provider-type", "issuer": "https://example.com"},
            headers=_headers(),
        )

    assert resp.status_code == 422


def test_authorize_with_a_null_byte_in_required_scope_returns_a_clean_422():
    """AuthorizationService.authorize persists `required_scope` verbatim into
    AuthDecisionRecord (the audit trail) on every call, allowed or denied --
    a NUL byte there reached Postgres unguarded before this fix."""
    app = _app(InMemoryIdentityAccessRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/identity-access/authorize",
            json={"token": "not-a-real-token", "required_scope": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422
