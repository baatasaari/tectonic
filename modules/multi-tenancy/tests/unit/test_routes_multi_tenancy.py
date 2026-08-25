"""API-level tests for the FastAPI routes -- the register -> suspend ->
reactivate/delete lifecycle, the gate check, and isolation probes
through a real app.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from multi_tenancy.api.deps import get_ctx, get_repository
from multi_tenancy.api.routes_multi_tenancy import router
from multi_tenancy.app_context import AppContext
from multi_tenancy.config import MultiTenancySettings
from multi_tenancy.core.fakes import InMemoryMultiTenancyRepository, StubTenantScopedListClient
from multi_tenancy.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository, *, probe_clients=None):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="multi-tenancy", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=MultiTenancySettings(), engine=None, session_factory=None,
        probe_clients=probe_clients or {"agent-cards": StubTenantScopedListClient()},
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="ci", audience="multi-tenancy", shared_secret=SECRET)


def _headers():
    return {"Authorization": f"Bearer {_token()}"}


def test_register_returns_an_active_tenant():
    app = _app(InMemoryMultiTenancyRepository())

    with TestClient(app) as client:
        resp = client.post("/v1/multi-tenancy/tenants", json={"name": "Acme Corp"}, headers=_headers())

    assert resp.status_code == 201
    assert resp.json()["status"] == "active"


def test_register_without_a_bearer_token_is_rejected():
    app = _app(InMemoryMultiTenancyRepository())

    with TestClient(app) as client:
        resp = client.post("/v1/multi-tenancy/tenants", json={"name": "Acme Corp"})

    assert resp.status_code == 401


def test_suspend_reactivate_delete_flow():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        tenant = client.post("/v1/multi-tenancy/tenants", json={"name": "Acme Corp"}, headers=headers).json()

        suspended = client.post(
            f"/v1/multi-tenancy/tenants/{tenant['id']}/suspend", json={"reason": "non-payment"}, headers=headers,
        ).json()
        assert suspended["status"] == "suspended"

        gate_while_suspended = client.get(
            f"/v1/multi-tenancy/tenants/{tenant['id']}/gate", headers=headers,
        ).json()
        assert gate_while_suspended["allowed"] is False

        reactivated = client.post(f"/v1/multi-tenancy/tenants/{tenant['id']}/reactivate", headers=headers).json()
        assert reactivated["status"] == "active"

        deleted = client.post(f"/v1/multi-tenancy/tenants/{tenant['id']}/delete", headers=headers).json()
        assert deleted["status"] == "deleted"

        resp = client.post(f"/v1/multi-tenancy/tenants/{tenant['id']}/reactivate", headers=headers)

    assert resp.status_code == 409


def test_get_tenant_returns_404_when_missing():
    app = _app(InMemoryMultiTenancyRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/multi-tenancy/tenants/does-not-exist", headers=_headers())

    assert resp.status_code == 404


def test_run_isolation_probe_detects_a_breach():
    client_stub = StubTenantScopedListClient(items=[
        {"id": "c1", "tenant_id": "acme"}, {"id": "c2", "tenant_id": "someone-else"},
    ])
    app = _app(InMemoryMultiTenancyRepository(), probe_clients={"agent-cards": client_stub})
    headers = _headers()

    with TestClient(app) as client:
        resp = client.post(
            "/v1/multi-tenancy/isolation-probes",
            json={"tenant_id": "acme", "target_name": "agent-cards"}, headers=headers,
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["passed"] is False
    assert body["breach_count"] == 1


def test_run_isolation_probe_returns_404_for_unregistered_target():
    app = _app(InMemoryMultiTenancyRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/multi-tenancy/isolation-probes",
            json={"tenant_id": "acme", "target_name": "unknown-module"}, headers=_headers(),
        )

    assert resp.status_code == 404


def test_list_isolation_probes():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        client.post(
            "/v1/multi-tenancy/isolation-probes",
            json={"tenant_id": "acme", "target_name": "agent-cards"}, headers=headers,
        )

        resp = client.get("/v1/multi-tenancy/isolation-probes", params={"tenant_id": "acme"}, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["total"] == 1
