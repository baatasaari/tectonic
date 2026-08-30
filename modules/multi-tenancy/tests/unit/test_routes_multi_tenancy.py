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
from multi_tenancy.core.fakes import (
    InMemoryEventPublisher,
    InMemoryMultiTenancyRepository,
    StubAuditabilityClient,
    StubTenantScopedListClient,
)
from multi_tenancy.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository, *, probe_clients=None, auditability=None):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="multi-tenancy", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=MultiTenancySettings(), engine=None, session_factory=None,
        auditability=auditability or StubAuditabilityClient(),
        event_publisher=InMemoryEventPublisher(),
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


def test_entitlements_round_trip_and_gate_by_module():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        tenant = client.post("/v1/multi-tenancy/tenants", json={"name": "Acme Corp"}, headers=headers).json()
        tenant_id = tenant["id"]

        unconfigured = client.get(f"/v1/multi-tenancy/tenants/{tenant_id}/entitlements", headers=headers).json()
        assert unconfigured == {"tenant_id": tenant_id, "module_names": [], "configured": False}

        gate_before = client.get(
            f"/v1/multi-tenancy/tenants/{tenant_id}/gate", params={"module": "agent-cards"}, headers=headers,
        ).json()
        assert gate_before["allowed"] is True

        set_resp = client.post(
            f"/v1/multi-tenancy/tenants/{tenant_id}/entitlements",
            json={"module_names": ["agent-cards", "guardrails"]}, headers=headers,
        )
        assert set_resp.status_code == 200
        body = set_resp.json()
        assert body["configured"] is True
        assert sorted(body["module_names"]) == ["agent-cards", "guardrails"]

        gate_allowed = client.get(
            f"/v1/multi-tenancy/tenants/{tenant_id}/gate", params={"module": "agent-cards"}, headers=headers,
        ).json()
        assert gate_allowed["allowed"] is True

        gate_denied = client.get(
            f"/v1/multi-tenancy/tenants/{tenant_id}/gate", params={"module": "finops"}, headers=headers,
        ).json()
        assert gate_denied["allowed"] is False
        assert "finops" in gate_denied["reason"]

        listed = client.get(f"/v1/multi-tenancy/tenants/{tenant_id}/entitlements", headers=headers).json()
        assert listed["configured"] is True
        assert sorted(listed["module_names"]) == ["agent-cards", "guardrails"]


def test_set_entitlements_returns_404_for_an_unknown_tenant():
    app = _app(InMemoryMultiTenancyRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/multi-tenancy/tenants/does-not-exist/entitlements",
            json={"module_names": ["agent-cards"]}, headers=_headers(),
        )

    assert resp.status_code == 404


def test_list_entitlements_returns_404_for_an_unknown_tenant():
    app = _app(InMemoryMultiTenancyRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/multi-tenancy/tenants/does-not-exist/entitlements", headers=_headers())

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


def test_list_isolation_probes_rejects_a_null_byte_in_target_name_with_a_clean_422():
    """Ticket #82: a real CI run of this module's own contract tier found
    this -- `target_name` is a raw `Query()` string, which (unlike a
    Pydantic body field) never runs through `_reject_null_byte`, so a NUL
    byte reached Postgres raw and 500'd instead of a clean 422."""
    app = _app(InMemoryMultiTenancyRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/multi-tenancy/isolation-probes", params={"target_name": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


# --- Organisation / Workspace / Environment (platform hierarchy control plane) ---


def test_organisation_lifecycle():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        org = client.post(
            "/v1/multi-tenancy/organisations", json={"name": "Acme Holdings"}, headers=headers,
        ).json()
        assert org["status"] == "active"
        assert org["version"] == 1

        fetched = client.get(f"/v1/multi-tenancy/organisations/{org['id']}", headers=headers).json()
        assert fetched["id"] == org["id"]

        suspended = client.post(
            f"/v1/multi-tenancy/organisations/{org['id']}/suspend",
            json={"reason": "review", "expected_version": org["version"]}, headers=headers,
        ).json()
        assert suspended["status"] == "suspended"

        reactivated = client.post(
            f"/v1/multi-tenancy/organisations/{org['id']}/reactivate",
            json={"expected_version": suspended["version"]}, headers=headers,
        ).json()
        assert reactivated["status"] == "active"

        deleted = client.post(
            f"/v1/multi-tenancy/organisations/{org['id']}/delete",
            json={"expected_version": reactivated["version"]}, headers=headers,
        ).json()
        assert deleted["status"] == "deleted"

        resp = client.post(
            f"/v1/multi-tenancy/organisations/{org['id']}/reactivate",
            json={"expected_version": deleted["version"]}, headers=headers,
        )

    assert resp.status_code == 409


def test_get_organisation_returns_404_when_missing():
    app = _app(InMemoryMultiTenancyRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/multi-tenancy/organisations/does-not-exist", headers=_headers())

    assert resp.status_code == 404


def test_list_organisations_filters_by_status():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        active = client.post(
            "/v1/multi-tenancy/organisations", json={"name": "Active Holdings"}, headers=headers,
        ).json()
        suspended = client.post(
            "/v1/multi-tenancy/organisations", json={"name": "Suspended Holdings"}, headers=headers,
        ).json()
        client.post(
            f"/v1/multi-tenancy/organisations/{suspended['id']}/suspend",
            json={"reason": "r", "expected_version": suspended["version"]}, headers=headers,
        )

        resp = client.get("/v1/multi-tenancy/organisations", params={"status": "active"}, headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == active["id"]


def test_tenant_can_be_registered_under_an_organisation():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        org = client.post(
            "/v1/multi-tenancy/organisations", json={"name": "Acme Holdings"}, headers=headers,
        ).json()
        tenant = client.post(
            "/v1/multi-tenancy/tenants", json={"name": "Acme Corp", "organisation_id": org["id"]}, headers=headers,
        ).json()

    assert tenant["organisation_id"] == org["id"]


def test_workspace_lifecycle():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        tenant = client.post("/v1/multi-tenancy/tenants", json={"name": "Acme Corp"}, headers=headers).json()
        ws = client.post(
            "/v1/multi-tenancy/workspaces",
            json={"tenant_id": tenant["id"], "name": "Production workflows"}, headers=headers,
        ).json()
        assert ws["status"] == "active"
        assert ws["tenant_id"] == tenant["id"]

        fetched = client.get(f"/v1/multi-tenancy/workspaces/{ws['id']}", headers=headers).json()
        assert fetched["id"] == ws["id"]

        suspended = client.post(
            f"/v1/multi-tenancy/workspaces/{ws['id']}/suspend",
            json={"reason": "incident", "expected_version": ws["version"]}, headers=headers,
        ).json()
        assert suspended["status"] == "suspended"

        reactivated = client.post(
            f"/v1/multi-tenancy/workspaces/{ws['id']}/reactivate",
            json={"expected_version": suspended["version"]}, headers=headers,
        ).json()
        assert reactivated["status"] == "active"

        deleted = client.post(
            f"/v1/multi-tenancy/workspaces/{ws['id']}/delete",
            json={"expected_version": reactivated["version"]}, headers=headers,
        ).json()
        assert deleted["status"] == "deleted"


def test_register_workspace_returns_404_for_an_unknown_tenant():
    app = _app(InMemoryMultiTenancyRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/multi-tenancy/workspaces",
            json={"tenant_id": "does-not-exist", "name": "Production workflows"}, headers=_headers(),
        )

    assert resp.status_code == 404


def test_list_workspaces_filters_by_tenant():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        tenant_a = client.post("/v1/multi-tenancy/tenants", json={"name": "Acme Corp"}, headers=headers).json()
        tenant_b = client.post("/v1/multi-tenancy/tenants", json={"name": "Globex Corp"}, headers=headers).json()
        ws_a = client.post(
            "/v1/multi-tenancy/workspaces", json={"tenant_id": tenant_a["id"], "name": "A"}, headers=headers,
        ).json()
        client.post(
            "/v1/multi-tenancy/workspaces", json={"tenant_id": tenant_b["id"], "name": "B"}, headers=headers,
        )

        resp = client.get("/v1/multi-tenancy/workspaces", params={"tenant_id": tenant_a["id"]}, headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == ws_a["id"]


def test_environment_lifecycle():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        tenant = client.post("/v1/multi-tenancy/tenants", json={"name": "Acme Corp"}, headers=headers).json()
        ws = client.post(
            "/v1/multi-tenancy/workspaces",
            json={"tenant_id": tenant["id"], "name": "Production workflows"}, headers=headers,
        ).json()
        env = client.post(
            "/v1/multi-tenancy/environments",
            json={"workspace_id": ws["id"], "name": "production", "kind": "production", "region": "eu-west-1"},
            headers=headers,
        ).json()
        assert env["status"] == "active"
        assert env["workspace_id"] == ws["id"]
        assert env["kind"] == "production"
        assert env["region"] == "eu-west-1"

        fetched = client.get(f"/v1/multi-tenancy/environments/{env['id']}", headers=headers).json()
        assert fetched["id"] == env["id"]

        suspended = client.post(
            f"/v1/multi-tenancy/environments/{env['id']}/suspend",
            json={"reason": "incident", "expected_version": env["version"]}, headers=headers,
        ).json()
        assert suspended["status"] == "suspended"

        reactivated = client.post(
            f"/v1/multi-tenancy/environments/{env['id']}/reactivate",
            json={"expected_version": suspended["version"]}, headers=headers,
        ).json()
        assert reactivated["status"] == "active"

        deleted = client.post(
            f"/v1/multi-tenancy/environments/{env['id']}/delete",
            json={"expected_version": reactivated["version"]}, headers=headers,
        ).json()
        assert deleted["status"] == "deleted"


def test_register_environment_returns_404_for_an_unknown_workspace():
    app = _app(InMemoryMultiTenancyRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/multi-tenancy/environments",
            json={"workspace_id": "does-not-exist", "name": "production"}, headers=_headers(),
        )

    assert resp.status_code == 404


def test_list_environments_filters_by_workspace():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        tenant = client.post("/v1/multi-tenancy/tenants", json={"name": "Acme Corp"}, headers=headers).json()
        ws_a = client.post(
            "/v1/multi-tenancy/workspaces", json={"tenant_id": tenant["id"], "name": "A"}, headers=headers,
        ).json()
        ws_b = client.post(
            "/v1/multi-tenancy/workspaces", json={"tenant_id": tenant["id"], "name": "B"}, headers=headers,
        ).json()
        env_a = client.post(
            "/v1/multi-tenancy/environments", json={"workspace_id": ws_a["id"], "name": "prod-a"}, headers=headers,
        ).json()
        client.post(
            "/v1/multi-tenancy/environments", json={"workspace_id": ws_b["id"], "name": "prod-b"}, headers=headers,
        )

        resp = client.get("/v1/multi-tenancy/environments", params={"workspace_id": ws_a["id"]}, headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == env_a["id"]


# --- Quota Set / real-time quota enforcement ---


def test_get_quota_set_before_any_limits_are_set_is_unconfigured():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        tenant = client.post("/v1/multi-tenancy/tenants", json={"name": "Acme Corp"}, headers=headers).json()
        resp = client.get(f"/v1/multi-tenancy/tenants/{tenant['id']}/quota-set", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is False
    assert body["limits"] == {}


def test_get_quota_set_returns_404_for_an_unknown_tenant():
    app = _app(InMemoryMultiTenancyRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/multi-tenancy/tenants/does-not-exist/quota-set", headers=_headers())

    assert resp.status_code == 404


def test_set_and_get_quota_set_round_trips():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        tenant = client.post("/v1/multi-tenancy/tenants", json={"name": "Acme Corp"}, headers=headers).json()
        set_resp = client.post(
            f"/v1/multi-tenancy/tenants/{tenant['id']}/quota-set",
            json={"limits": {"requests_per_minute": 600, "storage_gb": 500}}, headers=headers,
        )
        get_resp = client.get(f"/v1/multi-tenancy/tenants/{tenant['id']}/quota-set", headers=headers)

    assert set_resp.status_code == 200
    assert set_resp.json()["configured"] is True
    assert get_resp.json()["limits"] == {"requests_per_minute": 600, "storage_gb": 500}


def test_get_residency_policy_before_any_regions_are_set_is_unconfigured():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        tenant = client.post("/v1/multi-tenancy/tenants", json={"name": "Acme Corp"}, headers=headers).json()
        resp = client.get(f"/v1/multi-tenancy/tenants/{tenant['id']}/residency-policy", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is False
    assert body["allowed_regions"] == []


def test_get_residency_policy_returns_404_for_an_unknown_tenant():
    app = _app(InMemoryMultiTenancyRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/multi-tenancy/tenants/does-not-exist/residency-policy", headers=_headers())

    assert resp.status_code == 404


def test_set_and_get_residency_policy_round_trips():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        tenant = client.post("/v1/multi-tenancy/tenants", json={"name": "Acme Corp"}, headers=headers).json()
        set_resp = client.post(
            f"/v1/multi-tenancy/tenants/{tenant['id']}/residency-policy",
            json={"allowed_regions": ["eu-west-1", "us-east-1"]}, headers=headers,
        )
        get_resp = client.get(f"/v1/multi-tenancy/tenants/{tenant['id']}/residency-policy", headers=headers)

    assert set_resp.status_code == 200
    assert set_resp.json()["configured"] is True
    assert get_resp.json()["allowed_regions"] == ["eu-west-1", "us-east-1"]


def test_registering_an_environment_outside_the_residency_policy_is_rejected():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        tenant = client.post("/v1/multi-tenancy/tenants", json={"name": "Acme Corp"}, headers=headers).json()
        ws = client.post(
            "/v1/multi-tenancy/workspaces",
            json={"tenant_id": tenant["id"], "name": "Production"}, headers=headers,
        ).json()
        client.post(
            f"/v1/multi-tenancy/tenants/{tenant['id']}/residency-policy",
            json={"allowed_regions": ["eu-west-1"]}, headers=headers,
        )

        allowed = client.post(
            "/v1/multi-tenancy/environments",
            json={"workspace_id": ws["id"], "name": "prod-eu", "region": "eu-west-1"}, headers=headers,
        )
        rejected = client.post(
            "/v1/multi-tenancy/environments",
            json={"workspace_id": ws["id"], "name": "prod-us", "region": "us-east-1"}, headers=headers,
        )

    assert allowed.status_code == 201
    assert rejected.status_code == 422


def test_check_quota_allows_an_unconfigured_tenant():
    app = _app(InMemoryMultiTenancyRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/multi-tenancy/tenants/acme/quota/check",
            json={"resource_class": "requests_per_minute", "amount": 1}, headers=_headers(),
        )

    assert resp.status_code == 200
    assert resp.json()["allowed"] is True


def test_check_quota_denies_once_the_rate_limit_is_exceeded():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        tenant = client.post("/v1/multi-tenancy/tenants", json={"name": "Acme Corp"}, headers=headers).json()
        set_resp = client.post(
            f"/v1/multi-tenancy/tenants/{tenant['id']}/quota-set",
            json={"limits": {"requests_per_minute": 1}}, headers=headers,
        )
        assert set_resp.status_code == 200
        first = client.post(
            f"/v1/multi-tenancy/tenants/{tenant['id']}/quota/check",
            json={"resource_class": "requests_per_minute"}, headers=headers,
        )
        second = client.post(
            f"/v1/multi-tenancy/tenants/{tenant['id']}/quota/check",
            json={"resource_class": "requests_per_minute"}, headers=headers,
        )

    assert first.json()["allowed"] is True
    assert second.json()["allowed"] is False


def test_check_quota_returns_400_when_a_capacity_shaped_class_is_missing_current_usage():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        tenant = client.post("/v1/multi-tenancy/tenants", json={"name": "Acme Corp"}, headers=headers).json()
        set_resp = client.post(
            f"/v1/multi-tenancy/tenants/{tenant['id']}/quota-set",
            json={"limits": {"storage_gb": 500}}, headers=headers,
        )
        assert set_resp.status_code == 200
        resp = client.post(
            f"/v1/multi-tenancy/tenants/{tenant['id']}/quota/check",
            json={"resource_class": "storage_gb"}, headers=headers,
        )

    assert resp.status_code == 400


# --- Resource Allocation ---


def _make_environment(client, headers):
    tenant = client.post("/v1/multi-tenancy/tenants", json={"name": "Acme Corp"}, headers=headers).json()
    ws = client.post(
        "/v1/multi-tenancy/workspaces", json={"tenant_id": tenant["id"], "name": "Production"}, headers=headers,
    ).json()
    return client.post(
        "/v1/multi-tenancy/environments", json={"workspace_id": ws["id"], "name": "production"}, headers=headers,
    ).json()


def test_request_resource_allocation_returns_404_for_an_unknown_environment():
    app = _app(InMemoryMultiTenancyRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/multi-tenancy/resource-allocations",
            json={"environment_id": "does-not-exist", "resources": {"cpu_cores": 4}}, headers=_headers(),
        )

    assert resp.status_code == 404


def test_first_request_is_requested_then_approve_makes_it_active():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        env = _make_environment(client, headers)
        requested = client.post(
            "/v1/multi-tenancy/resource-allocations",
            json={"environment_id": env["id"], "resources": {"cpu_cores": 4}, "requested_by": "alice"},
            headers=headers,
        ).json()
        assert requested["status"] == "requested"

        approved = client.post(
            f"/v1/multi-tenancy/resource-allocations/{requested['id']}/approve",
            json={"approved_by": "platform-admin", "expected_version": requested["version"]}, headers=headers,
        )

    assert approved.status_code == 200
    assert approved.json()["status"] == "active"
    assert approved.json()["approved_by"] == "platform-admin"


def test_reject_stores_the_reason_and_is_terminal():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        env = _make_environment(client, headers)
        requested = client.post(
            "/v1/multi-tenancy/resource-allocations",
            json={"environment_id": env["id"], "resources": {"cpu_cores": 4}}, headers=headers,
        ).json()

        rejected = client.post(
            f"/v1/multi-tenancy/resource-allocations/{requested['id']}/reject",
            json={"reason": "over regional capacity", "expected_version": requested["version"]}, headers=headers,
        )
        reapprove = client.post(
            f"/v1/multi-tenancy/resource-allocations/{requested['id']}/approve",
            json={"approved_by": "platform-admin", "expected_version": rejected.json()["version"]}, headers=headers,
        )

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_reason"] == "over regional capacity"
    assert reapprove.status_code == 409


def test_get_resource_allocation_returns_404_for_an_unknown_id():
    app = _app(InMemoryMultiTenancyRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/multi-tenancy/resource-allocations/does-not-exist", headers=_headers())

    assert resp.status_code == 404


def test_list_resource_allocations_filters_by_environment():
    app = _app(InMemoryMultiTenancyRepository())
    headers = _headers()

    with TestClient(app) as client:
        env_a = _make_environment(client, headers)
        env_b = _make_environment(client, headers)
        allocation_a = client.post(
            "/v1/multi-tenancy/resource-allocations",
            json={"environment_id": env_a["id"], "resources": {"cpu_cores": 4}}, headers=headers,
        ).json()
        client.post(
            "/v1/multi-tenancy/resource-allocations",
            json={"environment_id": env_b["id"], "resources": {"cpu_cores": 4}}, headers=headers,
        )

        resp = client.get(
            "/v1/multi-tenancy/resource-allocations", params={"environment_id": env_a["id"]}, headers=headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == allocation_a["id"]
