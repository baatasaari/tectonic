"""Unit tests for service-to-service JWT auth (security/jwt_auth.py).

Covers the pure mint/verify functions directly (fast, no ASGI app needed)
plus one end-to-end pass through a real FastAPI app with
`ServiceAuthMiddleware` installed, proving the wiring itself — not just the
underlying functions — actually rejects/accepts requests correctly.
"""
from __future__ import annotations

import time

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_cards.security.jwt_auth import (
    ServiceAuthMiddleware,
    ServiceBearerAuth,
    mint_service_token,
    verify_service_token,
)

SECRET = "test-shared-secret-at-least-32-bytes-long"


def test_mint_and_verify_round_trip():
    token = mint_service_token(issuer="caller", audience="callee", shared_secret=SECRET)

    claims = verify_service_token(token, audience="callee", shared_secret=SECRET)

    assert claims["iss"] == "caller"
    assert claims["aud"] == "callee"


def test_verify_rejects_wrong_audience():
    token = mint_service_token(issuer="caller", audience="service-a", shared_secret=SECRET)

    with pytest.raises(pyjwt.InvalidAudienceError):
        verify_service_token(token, audience="service-b", shared_secret=SECRET)


def test_verify_rejects_wrong_secret():
    token = mint_service_token(issuer="caller", audience="callee", shared_secret=SECRET)

    with pytest.raises(pyjwt.InvalidSignatureError):
        verify_service_token(token, audience="callee", shared_secret="a-completely-different-secret-value")


def test_verify_rejects_expired_token():
    token = mint_service_token(issuer="caller", audience="callee", shared_secret=SECRET, ttl_seconds=-1)

    with pytest.raises(pyjwt.ExpiredSignatureError):
        verify_service_token(token, audience="callee", shared_secret=SECRET)


def test_minted_token_expires_ttl_seconds_from_now():
    before = int(time.time())
    token = mint_service_token(issuer="caller", audience="callee", shared_secret=SECRET, ttl_seconds=120)
    claims = pyjwt.decode(token, SECRET, algorithms=["HS256"], audience="callee")

    assert before + 120 <= claims["exp"] <= before + 121


def _protected_app(*, audience: str, shared_secret: str) -> FastAPI:
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience=audience, shared_secret=shared_secret)

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


def test_middleware_excludes_healthz_and_metrics_from_auth():
    app = _protected_app(audience="this-service", shared_secret=SECRET)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/metrics").status_code == 200


def test_middleware_rejects_protected_route_without_a_token():
    app = _protected_app(audience="this-service", shared_secret=SECRET)
    with TestClient(app) as client:
        resp = client.get("/protected")

    assert resp.status_code == 401
    assert "missing bearer token" in resp.json()["detail"]


def test_middleware_accepts_a_valid_token_scoped_to_this_service():
    app = _protected_app(audience="this-service", shared_secret=SECRET)
    token = mint_service_token(issuer="caller", audience="this-service", shared_secret=SECRET)
    with TestClient(app) as client:
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_middleware_rejects_a_token_scoped_to_a_different_service():
    app = _protected_app(audience="this-service", shared_secret=SECRET)
    token = mint_service_token(issuer="caller", audience="some-other-service", shared_secret=SECRET)
    with TestClient(app) as client:
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401


async def test_service_bearer_auth_attaches_a_valid_bearer_header_to_outbound_requests():
    """The outbound half: an httpx.AsyncClient using ServiceBearerAuth against a peer
    running ServiceAuthMiddleware should be let straight through with zero manual header
    wiring at any call site."""
    import httpx

    peer_app = _protected_app(audience="peer-service", shared_secret=SECRET)
    auth = ServiceBearerAuth(issuer="this-service", audience="peer-service", shared_secret=SECRET)
    transport = httpx.ASGITransport(app=peer_app)

    async with httpx.AsyncClient(transport=transport, base_url="http://peer", auth=auth) as client:
        resp = await client.get("/protected")

    assert resp.status_code == 200
