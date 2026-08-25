"""API-level tests for the FastAPI routes -- create, list, retrieve
(the zero-trust gate through a real app), rotate, revoke, and
compliance.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from secrets_and_credential_management.api.deps import get_ctx, get_repository
from secrets_and_credential_management.api.routes_secrets_and_credential_management import router
from secrets_and_credential_management.app_context import AppContext
from secrets_and_credential_management.config import SecretsAndCredentialManagementSettings
from secrets_and_credential_management.core.fakes import (
    InMemorySecretsRepository,
    StubAuditabilityClient,
    StubIdentityAccessClient,
)
from secrets_and_credential_management.security.envelope_encryption import EnvelopeCipher
from secrets_and_credential_management.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET
MASTER_KEY = "TjDlTNIHnInVxA0zsGHYi6iTjBRtCSnWVcGxrYLXaYc="
AUDIENCE = "secrets-and-credential-management"


def _app(repository, *, identity_access=None, auditability=None):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience=AUDIENCE, shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=SecretsAndCredentialManagementSettings(), engine=None, session_factory=None,
        identity_access=identity_access or StubIdentityAccessClient(),
        auditability=auditability or StubAuditabilityClient(),
        cipher=EnvelopeCipher(master_key=MASTER_KEY),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="conversational-engine", audience=AUDIENCE, shared_secret=SECRET)


def _headers(**extra):
    return {"Authorization": f"Bearer {_token()}", **extra}


def test_create_and_get_secret():
    app = _app(InMemorySecretsRepository())

    with TestClient(app) as client:
        created = client.post(
            "/v1/secrets",
            json={"tenant_id": "acme", "namespace": "db", "key_name": "password", "value": "hunter2"},
            headers=_headers(),
        ).json()
        assert created["status"] == "active"
        assert created["current_version"] == 1

        fetched = client.get(f"/v1/secrets/{created['id']}", headers=_headers()).json()

    assert fetched["id"] == created["id"]


def test_secret_response_never_carries_the_value_or_ciphertext():
    app = _app(InMemorySecretsRepository())

    with TestClient(app) as client:
        created = client.post(
            "/v1/secrets",
            json={"tenant_id": "acme", "namespace": "db", "key_name": "password", "value": "hunter2"},
            headers=_headers(),
        ).json()

    assert "value" not in created
    assert "ciphertext" not in created


def test_without_a_bearer_token_is_rejected():
    app = _app(InMemorySecretsRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/secrets", headers={})

    assert resp.status_code == 401


def test_retrieve_allowed_returns_the_plaintext_value():
    app = _app(InMemorySecretsRepository(), identity_access=StubIdentityAccessClient(allow=True))

    with TestClient(app) as client:
        created = client.post(
            "/v1/secrets",
            json={"tenant_id": "acme", "namespace": "db", "key_name": "password", "value": "hunter2"},
            headers=_headers(),
        ).json()

        resp = client.post(
            f"/v1/secrets/{created['id']}/retrieve", json={"token": "a-token"}, headers=_headers(),
        ).json()

    assert resp["allowed"] is True
    assert resp["value"] == "hunter2"


def test_retrieve_denied_never_carries_a_value():
    app = _app(InMemorySecretsRepository(), identity_access=StubIdentityAccessClient(allow=False, reason="nope"))

    with TestClient(app) as client:
        created = client.post(
            "/v1/secrets",
            json={"tenant_id": "acme", "namespace": "db", "key_name": "password", "value": "hunter2"},
            headers=_headers(),
        ).json()

        resp = client.post(
            f"/v1/secrets/{created['id']}/retrieve", json={"token": "a-token"}, headers=_headers(),
        ).json()

    assert resp["allowed"] is False
    assert resp["value"] is None


def test_revoke_then_revoke_again_returns_409():
    app = _app(InMemorySecretsRepository())

    with TestClient(app) as client:
        created = client.post(
            "/v1/secrets",
            json={"tenant_id": "acme", "namespace": "db", "key_name": "password", "value": "hunter2"},
            headers=_headers(),
        ).json()

        first = client.post(f"/v1/secrets/{created['id']}/revoke", headers=_headers())
        assert first.json()["status"] == "revoked"

        second = client.post(f"/v1/secrets/{created['id']}/revoke", headers=_headers())

    assert second.status_code == 409


def test_rotate_advances_the_version():
    app = _app(InMemorySecretsRepository())

    with TestClient(app) as client:
        created = client.post(
            "/v1/secrets",
            json={"tenant_id": "acme", "namespace": "db", "key_name": "password", "value": "hunter2"},
            headers=_headers(),
        ).json()

        rotated = client.post(
            f"/v1/secrets/{created['id']}/rotate", json={"new_value": "new-password"}, headers=_headers(),
        ).json()

    assert rotated["current_version"] == 2


def test_get_secret_returns_404_when_missing():
    app = _app(InMemorySecretsRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/secrets/does-not-exist", headers=_headers())

    assert resp.status_code == 404


def test_compliance_endpoint_with_no_secrets_returns_none():
    app = _app(InMemorySecretsRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/secrets/compliance", params={"tenant_id": "empty"}, headers=_headers())

    assert resp.status_code == 200
    assert resp.json()["compliance_rate"] is None


def test_access_log_lists_retrieval_attempts():
    app = _app(InMemorySecretsRepository())

    with TestClient(app) as client:
        created = client.post(
            "/v1/secrets",
            json={"tenant_id": "acme", "namespace": "db", "key_name": "password", "value": "hunter2"},
            headers=_headers(),
        ).json()
        client.post(f"/v1/secrets/{created['id']}/retrieve", json={"token": "tok"}, headers=_headers())

        resp = client.get(f"/v1/secrets/{created['id']}/access-log", headers=_headers())

    assert resp.status_code == 200
    assert resp.json()["total"] == 1
