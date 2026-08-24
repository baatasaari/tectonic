"""API-level tests for the FastAPI routes -- tenant resolution from the
X-Tenant-Id header (this platform's standard convention, matching
Workflow Engine's own `resolve_tenant_id`), and the full register ->
set-policy -> rpc flow through a real app.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mcp_gateway.api.deps import get_ctx, get_repository
from mcp_gateway.api.routes_mcp import router
from mcp_gateway.app_context import AppContext
from mcp_gateway.config import MCPGatewaySettings
from mcp_gateway.core.fakes import InMemoryMCPGatewayRepository, StubMCPBackendClient
from mcp_gateway.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository, backend=None):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="mcp", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=MCPGatewaySettings(), engine=None, session_factory=None, backend=backend or StubMCPBackendClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="workflow-engine", audience="mcp", shared_secret=SECRET)


def test_register_uses_the_x_tenant_id_header():
    app = _app(InMemoryMCPGatewayRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/mcp/servers", json={"name": "search-tools", "base_url": "http://backend.example"},
            headers={"Authorization": f"Bearer {_token()}", "X-Tenant-Id": "acme"},
        )

    assert resp.status_code == 201
    assert resp.json()["tenant_id"] == "acme"


def test_register_without_a_bearer_token_is_rejected():
    app = _app(InMemoryMCPGatewayRepository())

    with TestClient(app) as client:
        resp = client.post("/v1/mcp/servers", json={"name": "s", "base_url": "http://b"})

    assert resp.status_code == 401


def test_full_register_policy_rpc_flow():
    repository = InMemoryMCPGatewayRepository()
    app = _app(repository)
    token = _token()
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-Id": "acme"}

    with TestClient(app) as client:
        server = client.post(
            "/v1/mcp/servers", json={"name": "s", "base_url": "http://backend.example"}, headers=headers,
        ).json()

        # No policy yet -- denied.
        denied = client.post(
            f"/v1/mcp/servers/{server['id']}/rpc", json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
            headers=headers,
        )
        assert denied.json()["error"] is not None

        client.put(f"/v1/mcp/servers/{server['id']}/access-policy", json={"allowed_tools": None}, headers=headers)

        allowed = client.post(
            f"/v1/mcp/servers/{server['id']}/rpc", json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
            headers=headers,
        )
        assert allowed.status_code == 200
        assert allowed.json()["result"] == {"ok": True}


def test_get_server_returns_404_for_an_unknown_id():
    app = _app(InMemoryMCPGatewayRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/mcp/servers/does-not-exist", headers={"Authorization": f"Bearer {_token()}"})

    assert resp.status_code == 404


def test_list_servers_returns_a_paginated_envelope():
    repository = InMemoryMCPGatewayRepository()
    app = _app(repository)
    headers = {"Authorization": f"Bearer {_token()}", "X-Tenant-Id": "acme"}

    with TestClient(app) as client:
        for i in range(3):
            client.post("/v1/mcp/servers", json={"name": f"s{i}", "base_url": f"http://{i}"}, headers=headers)
        resp = client.get("/v1/mcp/servers", params={"tenant_id": "acme", "limit": 2}, headers=headers)

    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 3
    assert len(body["items"]) == 2
