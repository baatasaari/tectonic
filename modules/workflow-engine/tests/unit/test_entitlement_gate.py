"""Unit tests for security/entitlement_gate.py -- EntitlementGateMiddleware,
this platform's reference implementation of the per-module feature-flag
check. Uses `httpx.MockTransport` to stand in for Multi-tenancy's real
gate endpoint, the same "no real peer, no network" pattern this
module's own outbound-client tests already use.
"""
from __future__ import annotations

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from workflow_engine.security.entitlement_gate import EntitlementGateMiddleware

MODULE_NAME = "workflow-engine"


def _client_returning(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="http://multi-tenancy", transport=httpx.MockTransport(handler))


def _app(client: httpx.AsyncClient, *, cache_ttl_seconds: float = 30.0) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        EntitlementGateMiddleware,
        module_name=MODULE_NAME,
        multi_tenancy_base_url="http://multi-tenancy",
        cache_ttl_seconds=cache_ttl_seconds,
        client=client,
    )

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/metrics")
    async def metrics():
        return "metrics"

    @app.get("/protected")
    async def protected():
        return {"ok": True}

    return app


def _allow_handler(calls: list):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        return httpx.Response(200, json={"allowed": True, "reason": "active"})
    return handler


def _deny_handler(calls: list, *, reason: str = "module not included in subscription: agent-cards"):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        return httpx.Response(200, json={"allowed": False, "reason": reason})
    return handler


def _raising_handler(calls: list):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        raise httpx.ConnectError("connection refused", request=request)
    return handler


def test_healthz_and_metrics_are_excluded_from_the_gate():
    calls: list = []
    app = _app(_client_returning(_allow_handler(calls)))

    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/metrics").status_code == 200

    assert calls == []


def test_no_tenant_header_passes_through_ungated():
    calls: list = []
    app = _app(_client_returning(_allow_handler(calls)))

    with TestClient(app) as client:
        resp = client.get("/protected")

    assert resp.status_code == 200
    assert calls == []


def test_an_entitled_tenant_is_allowed_through():
    calls: list = []
    app = _app(_client_returning(_allow_handler(calls)))

    with TestClient(app) as client:
        resp = client.get("/protected", headers={"X-Tenant-Id": "acme"})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert calls == [{"module": MODULE_NAME}]


def test_a_tenant_missing_the_module_is_denied_with_402():
    calls: list = []
    app = _app(_client_returning(_deny_handler(calls)))

    with TestClient(app) as client:
        resp = client.get("/protected", headers={"X-Tenant-Id": "acme"})

    assert resp.status_code == 402
    assert "agent-cards" in resp.json()["detail"]


def test_repeat_requests_within_the_cache_ttl_hit_multi_tenancy_once():
    calls: list = []
    app = _app(_client_returning(_allow_handler(calls)), cache_ttl_seconds=60.0)

    with TestClient(app) as client:
        client.get("/protected", headers={"X-Tenant-Id": "acme"})
        client.get("/protected", headers={"X-Tenant-Id": "acme"})
        client.get("/protected", headers={"X-Tenant-Id": "acme"})

    assert len(calls) == 1


def test_different_tenants_are_cached_independently():
    calls: list = []
    app = _app(_client_returning(_allow_handler(calls)), cache_ttl_seconds=60.0)

    with TestClient(app) as client:
        client.get("/protected", headers={"X-Tenant-Id": "acme"})
        client.get("/protected", headers={"X-Tenant-Id": "globex"})

    assert len(calls) == 2


def test_multi_tenancy_unreachable_fails_open():
    calls: list = []
    app = _app(_client_returning(_raising_handler(calls)))

    with TestClient(app) as client:
        resp = client.get("/protected", headers={"X-Tenant-Id": "acme"})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert len(calls) == 1


def test_a_suspended_tenants_reason_passes_through_unchanged():
    """The gate call denies for reasons other than a missing entitlement too
    (e.g. a suspended tenant) -- the middleware surfaces whatever reason
    Multi-tenancy's own gate() actually returned, not a canned string."""
    calls: list = []
    app = _app(_client_returning(_deny_handler(calls, reason="tenant is suspended")))

    with TestClient(app) as client:
        resp = client.get("/protected", headers={"X-Tenant-Id": "acme"})

    assert resp.status_code == 402
    assert resp.json()["detail"] == "tenant is suspended"
