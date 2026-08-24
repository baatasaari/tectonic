"""API-level tests for the FastAPI routes -- tenant resolution from the
X-Tenant-Id header, discovery ranking, and the recompute-trust-score
endpoint through a real app.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_cards.api.deps import get_ctx, get_repository
from agent_cards.api.routes_agent_cards import router
from agent_cards.app_context import AppContext
from agent_cards.config import AgentCardsSettings
from agent_cards.core.fakes import (
    InMemoryAgentCardsRepository,
    StubEvaluationFrameworkClient,
    StubRegulatoryComplianceClient,
)
from agent_cards.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository, *, evaluation_framework=None, regulatory_compliance=None):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="agent-cards", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=AgentCardsSettings(), engine=None, session_factory=None,
        evaluation_framework=evaluation_framework or StubEvaluationFrameworkClient(),
        regulatory_compliance=regulatory_compliance or StubRegulatoryComplianceClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="workflow-engine", audience="agent-cards", shared_secret=SECRET)


def test_register_uses_the_x_tenant_id_header():
    app = _app(InMemoryAgentCardsRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/agent-cards", json={"agent_ref": "a1", "name": "Agent One", "url": "http://a1.example"},
            headers={"Authorization": f"Bearer {_token()}", "X-Tenant-Id": "acme"},
        )

    assert resp.status_code == 201
    assert resp.json()["tenant_id"] == "acme"


def test_register_without_a_bearer_token_is_rejected():
    app = _app(InMemoryAgentCardsRepository())

    with TestClient(app) as client:
        resp = client.post("/v1/agent-cards", json={"agent_ref": "a1", "name": "a", "url": "http://a"})

    assert resp.status_code == 401


def test_get_card_returns_404_for_an_unknown_id():
    app = _app(InMemoryAgentCardsRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/agent-cards/does-not-exist", headers={"Authorization": f"Bearer {_token()}"})

    assert resp.status_code == 404


def test_discover_returns_a_paginated_envelope():
    app = _app(InMemoryAgentCardsRepository())
    headers = {"Authorization": f"Bearer {_token()}", "X-Tenant-Id": "acme"}

    with TestClient(app) as client:
        for i in range(3):
            client.post("/v1/agent-cards", json={"agent_ref": f"a{i}", "name": f"a{i}", "url": f"http://{i}"}, headers=headers)
        resp = client.get("/v1/agent-cards", params={"tenant_id": "acme", "limit": 2}, headers=headers)

    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_recompute_trust_score_persists_and_returns_the_breakdown():
    repository = InMemoryAgentCardsRepository()
    evalfw = StubEvaluationFrameworkClient(scores=[{"score": 1.0, "threshold": 1.0}])
    regcomp = StubRegulatoryComplianceClient(coverage_percentage=100.0)
    app = _app(repository, evaluation_framework=evalfw, regulatory_compliance=regcomp)
    headers = {"Authorization": f"Bearer {_token()}", "X-Tenant-Id": "acme"}

    with TestClient(app) as client:
        registered = client.post(
            "/v1/agent-cards", json={"agent_ref": "a1", "name": "a", "url": "http://a"}, headers=headers,
        ).json()

        resp = client.post(f"/v1/agent-cards/{registered['id']}/recompute-trust-score", headers=headers)

        refetched = client.get(f"/v1/agent-cards/{registered['id']}", headers=headers).json()

    assert resp.status_code == 200
    assert resp.json()["trust_score"] == 1.0
    assert refetched["trust_score"] == 1.0
