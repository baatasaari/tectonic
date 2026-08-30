"""API-level tests for the FastAPI routes -- developer registration
through a real app (real Identity and Access/Multi-tenancy stubs),
catalogue sync, SDK generation, and adoption metrics.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sdk_and_developer_portal.api.deps import get_ctx, get_repository
from sdk_and_developer_portal.api.routes_sdk_and_developer_portal import router
from sdk_and_developer_portal.app_context import AppContext
from sdk_and_developer_portal.config import CatalogTargetConfig, SdkAndDeveloperPortalSettings
from sdk_and_developer_portal.core.fakes import (
    InMemoryPortalRepository,
    StubAuditabilityClient,
    StubIdentityAccessClient,
    StubModuleSpecClient,
    StubMultiTenancyClient,
)
from sdk_and_developer_portal.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET
AUDIENCE = "sdk-and-developer-portal"

SPEC = {"info": {"title": "Auditability", "version": "1.0.0"}, "paths": {"/a": {"get": {"operationId": "a"}}}}


def _app(repository, *, identity_access=None, multi_tenancy=None, auditability=None, module_spec=None):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience=AUDIENCE, shared_secret=SECRET)
    app.include_router(router)

    settings = SdkAndDeveloperPortalSettings(
        catalog_targets=[CatalogTargetConfig(name="auditability", base_url="http://auditability.local")],
    )
    ctx = AppContext(
        settings=settings, engine=None, session_factory=None,
        identity_access=identity_access or StubIdentityAccessClient(),
        multi_tenancy=multi_tenancy or StubMultiTenancyClient(),
        auditability=auditability or StubAuditabilityClient(),
        module_spec=module_spec or StubModuleSpecClient({"auditability": SPEC}),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="conversational-engine", audience=AUDIENCE, shared_secret=SECRET)


def _headers(**extra):
    return {"Authorization": f"Bearer {_token()}", **extra}


def test_register_and_get_developer():
    app = _app(InMemoryPortalRepository())

    with TestClient(app) as client:
        created = client.post(
            "/v1/sdk-portal/developers", json={"name": "Ada", "email": "ada@example.com"}, headers=_headers(),
        ).json()
        assert created["status"] == "active"

        fetched = client.get(f"/v1/sdk-portal/developers/{created['id']}", headers=_headers()).json()

    assert fetched["id"] == created["id"]


def test_without_a_bearer_token_is_rejected():
    app = _app(InMemoryPortalRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/sdk-portal/developers")

    assert resp.status_code == 401


def test_revoke_then_revoke_again_returns_409():
    app = _app(InMemoryPortalRepository())

    with TestClient(app) as client:
        created = client.post(
            "/v1/sdk-portal/developers", json={"name": "Ada", "email": "ada@example.com"}, headers=_headers(),
        ).json()

        first = client.post(f"/v1/sdk-portal/developers/{created['id']}/revoke", headers=_headers())
        assert first.json()["status"] == "revoked"

        second = client.post(f"/v1/sdk-portal/developers/{created['id']}/revoke", headers=_headers())

    assert second.status_code == 409


def test_issue_sandbox_token_for_a_revoked_developer_returns_403():
    app = _app(InMemoryPortalRepository())

    with TestClient(app) as client:
        created = client.post(
            "/v1/sdk-portal/developers", json={"name": "Ada", "email": "ada@example.com"}, headers=_headers(),
        ).json()
        client.post(f"/v1/sdk-portal/developers/{created['id']}/revoke", headers=_headers())

        resp = client.post(f"/v1/sdk-portal/developers/{created['id']}/token", json={}, headers=_headers())

    assert resp.status_code == 403


def test_catalog_sync_and_generate_sdk_flow():
    app = _app(InMemoryPortalRepository())

    with TestClient(app) as client:
        synced = client.post("/v1/sdk-portal/catalog/sync", headers=_headers()).json()
        assert len(synced) == 1
        assert synced[0]["module_name"] == "auditability"

        entry = client.get("/v1/sdk-portal/catalog/auditability", headers=_headers()).json()
        assert entry["path_count"] == 1

        generated = client.post(
            "/v1/sdk-portal/sdks/generate", json={"module_name": "auditability", "language": "python"},
            headers=_headers(),
        ).json()
        assert generated["version"] == 1
        assert "def a(self, **kwargs)" in generated["source_code"]

        fetched = client.get(f"/v1/sdk-portal/sdks/{generated['id']}", headers=_headers()).json()

    assert fetched["id"] == generated["id"]


def test_generate_sdk_for_an_uncatalogued_module_returns_404():
    app = _app(InMemoryPortalRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/sdk-portal/sdks/generate", json={"module_name": "does-not-exist"}, headers=_headers(),
        )

    assert resp.status_code == 404


def test_adoption_endpoints_with_no_activity():
    app = _app(InMemoryPortalRepository())

    with TestClient(app) as client:
        created = client.post(
            "/v1/sdk-portal/developers", json={"name": "Ada", "email": "ada@example.com"}, headers=_headers(),
        ).json()

        adoption = client.get(f"/v1/sdk-portal/developers/{created['id']}/adoption", headers=_headers()).json()
        assert adoption["first_call_at"] is None

        rate = client.get("/v1/sdk-portal/adoption-rate", headers=_headers()).json()
        assert rate["total_developers"] == 1
        assert rate["adopted_count"] == 0


def test_list_developers_rejects_a_status_that_is_not_a_real_developer_status():
    """`status` used to be a bare `str` hand-converted to `DeveloperStatus`,
    raising an unhandled `ValueError` (500) for any non-member string --
    now typed `DeveloperStatus` directly so FastAPI/Pydantic rejects it
    with a clean 422."""
    app = _app(InMemoryPortalRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/sdk-portal/developers", params={"status": "not-a-real-status"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_list_sdks_rejects_a_null_byte_in_module_name_with_a_clean_422():
    """Ticket #82: a raw `Query()` string never runs through a Pydantic
    body field's own NUL-byte validator, so this reached the repository
    (and, against real Postgres, the database itself) raw instead of a
    clean 422."""
    app = _app(InMemoryPortalRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/sdk-portal/sdks", params={"module_name": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422
