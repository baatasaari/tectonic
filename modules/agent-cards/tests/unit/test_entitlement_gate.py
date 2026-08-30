"""Unit tests for security/entitlement_gate.py -- EntitlementGateMiddleware,
this platform's reference implementation of the per-module feature-flag
check. Uses `httpx.MockTransport` to stand in for Multi-tenancy's real
gate endpoint, the same "no real peer, no network" pattern this
module's own outbound-client tests already use.
"""
from __future__ import annotations

import time

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_cards.security.entitlement_gate import EntitlementGateMiddleware

MODULE_NAME = "agent-cards"


def _client_returning(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="http://multi-tenancy", transport=httpx.MockTransport(handler))


def _app(
    client: httpx.AsyncClient, *, cache_ttl_seconds: float = 30.0,
    max_staleness_seconds: float = 300.0, shared_secret: str = "test-secret",
) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        EntitlementGateMiddleware,
        module_name=MODULE_NAME,
        multi_tenancy_base_url="http://multi-tenancy",
        cache_ttl_seconds=cache_ttl_seconds,
        max_staleness_seconds=max_staleness_seconds,
        shared_secret=shared_secret,
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


def test_multi_tenancy_unreachable_with_no_cached_decision_fails_closed():
    """The bounded-staleness cache's whole point: a cold cache with Multi-
    tenancy already unreachable must deny, not silently allow -- the
    opposite of this middleware's old unconditional fail-open posture."""
    calls: list = []
    app = _app(_client_returning(_raising_handler(calls)))

    with TestClient(app) as client:
        resp = client.get("/protected", headers={"X-Tenant-Id": "acme"})

    assert resp.status_code == 402
    assert "unavailable" in resp.json()["detail"]
    assert len(calls) == 1


def test_an_outage_within_the_staleness_window_serves_the_last_verified_decision():
    """A decision verified once, then an outage inside cache_ttl+staleness
    bound -- the last real (allowed=True) decision is still served."""
    calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        if len(calls) == 1:
            return httpx.Response(200, json={"allowed": True, "reason": "active"})
        raise httpx.ConnectError("connection refused", request=request)

    app = _app(_client_returning(handler), cache_ttl_seconds=0.01, max_staleness_seconds=300.0)

    with TestClient(app) as client:
        first = client.get("/protected", headers={"X-Tenant-Id": "acme"})
        time.sleep(0.02)  # let the cache_ttl elapse so the next call re-checks live
        second = client.get("/protected", headers={"X-Tenant-Id": "acme"})

    assert first.status_code == 200
    assert second.status_code == 200  # served the stale-but-bounded verified decision
    assert len(calls) == 2


def test_an_outage_past_the_staleness_bound_fails_closed_even_with_prior_verification():
    """A previously-verified ALLOW decision must stop being served once it
    is older than max_staleness_seconds -- staleness is bounded, not
    indefinite fail-open in a different shape."""
    def handler(request: httpx.Request) -> httpx.Response:
        if handler.calls == 0:
            handler.calls += 1
            return httpx.Response(200, json={"allowed": True, "reason": "active"})
        handler.calls += 1
        raise httpx.ConnectError("connection refused", request=request)
    handler.calls = 0

    app = _app(
        _client_returning(handler), cache_ttl_seconds=0.01, max_staleness_seconds=0.02,
    )

    with TestClient(app) as client:
        first = client.get("/protected", headers={"X-Tenant-Id": "acme"})
        time.sleep(0.05)  # outlast both cache_ttl and max_staleness
        second = client.get("/protected", headers={"X-Tenant-Id": "acme"})

    assert first.status_code == 200
    assert second.status_code == 402
    assert "unavailable" in second.json()["detail"]


def test_a_previously_denied_decision_is_still_denied_when_served_stale():
    """The stale-serve path replays whatever the last VERIFIED decision was
    -- a real prior DENY stays a 402 during a bounded outage, it does not
    flip to allow just because Multi-tenancy is unreachable."""
    def handler(request: httpx.Request) -> httpx.Response:
        if handler.calls == 0:
            handler.calls += 1
            return httpx.Response(200, json={"allowed": False, "reason": "tenant is suspended"})
        handler.calls += 1
        raise httpx.ConnectError("connection refused", request=request)
    handler.calls = 0

    app = _app(_client_returning(handler), cache_ttl_seconds=0.01, max_staleness_seconds=300.0)

    with TestClient(app) as client:
        first = client.get("/protected", headers={"X-Tenant-Id": "acme"})
        time.sleep(0.02)
        second = client.get("/protected", headers={"X-Tenant-Id": "acme"})

    assert first.status_code == 402
    assert second.status_code == 402
    assert second.json()["detail"] == "tenant is suspended"


def test_a_cache_entry_with_a_forged_signature_is_never_trusted():
    """Defense in depth for the signed cache: an entry whose signature does
    not match its content (corruption, or a future shared-store write from
    something else) must be treated as absent, not as verified -- proven
    here by constructing the middleware, then directly corrupting its
    internal cache dict before the next stale-serve decision."""
    def handler(request: httpx.Request) -> httpx.Response:
        if handler.calls == 0:
            handler.calls += 1
            return httpx.Response(200, json={"allowed": True, "reason": "active"})
        handler.calls += 1
        raise httpx.ConnectError("connection refused", request=request)
    handler.calls = 0

    app = _app(_client_returning(handler), cache_ttl_seconds=0.01, max_staleness_seconds=300.0)

    with TestClient(app) as client:
        first = client.get("/protected", headers={"X-Tenant-Id": "acme"})
        assert first.status_code == 200

        # Reach into the middleware and corrupt the cached decision's signature.
        # Starlette wraps middleware lazily; walk the built stack after a request
        # has been made to find the live EntitlementGateMiddleware instance.
        stack = app.middleware_stack
        node = stack
        instance = None
        seen = set()
        while node is not None and id(node) not in seen:
            seen.add(id(node))
            if isinstance(node, EntitlementGateMiddleware):
                instance = node
                break
            node = getattr(node, "app", None)
        assert instance is not None
        cached = instance._cache["acme"]
        instance._cache["acme"] = cached.__class__(
            allowed=cached.allowed, reason=cached.reason,
            verified_at=cached.verified_at, signature="0" * 64,
        )

        time.sleep(0.02)
        second = client.get("/protected", headers={"X-Tenant-Id": "acme"})

    # The forged entry is rejected -> treated as no cached decision -> live
    # call attempted -> that call also fails -> fail closed.
    assert second.status_code == 402
    assert "unavailable" in second.json()["detail"]
