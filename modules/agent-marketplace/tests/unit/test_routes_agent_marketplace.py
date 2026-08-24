"""API-level tests for the FastAPI routes -- tenant resolution from the
X-Tenant-Id header, the full submit -> approve -> search -> record-usage
flow, and the illegal-transition 409 through a real app.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_marketplace.api.deps import get_ctx, get_repository
from agent_marketplace.api.routes_agent_marketplace import router
from agent_marketplace.app_context import AppContext
from agent_marketplace.config import AgentMarketplaceSettings
from agent_marketplace.core.fakes import InMemoryAgentMarketplaceRepository, StubAgentCardsClient
from agent_marketplace.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository, *, agent_cards=None):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="agent-marketplace", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=AgentMarketplaceSettings(), engine=None, session_factory=None,
        agent_cards=agent_cards or StubAgentCardsClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="workflow-engine", audience="agent-marketplace", shared_secret=SECRET)


def test_submit_uses_the_x_tenant_id_header():
    app = _app(InMemoryAgentMarketplaceRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/agent-marketplace/listings", json={"agent_card_id": "card-1", "submitted_by": "alice"},
            headers={"Authorization": f"Bearer {_token()}", "X-Tenant-Id": "acme"},
        )

    assert resp.status_code == 201
    assert resp.json()["tenant_id"] == "acme"
    assert resp.json()["status"] == "pending_review"


def test_submit_without_a_bearer_token_is_rejected():
    app = _app(InMemoryAgentMarketplaceRepository())

    with TestClient(app) as client:
        resp = client.post("/v1/agent-marketplace/listings", json={"agent_card_id": "card-1"})

    assert resp.status_code == 401


def test_submit_returns_404_for_an_unknown_agent_card():
    app = _app(InMemoryAgentMarketplaceRepository(), agent_cards=StubAgentCardsClient(card=None))

    with TestClient(app) as client:
        resp = client.post(
            "/v1/agent-marketplace/listings", json={"agent_card_id": "does-not-exist"},
            headers={"Authorization": f"Bearer {_token()}"},
        )

    assert resp.status_code == 404


def test_full_submit_approve_search_record_usage_flow():
    repository = InMemoryAgentMarketplaceRepository()
    app = _app(repository)
    headers = {"Authorization": f"Bearer {_token()}", "X-Tenant-Id": "acme"}

    with TestClient(app) as client:
        submitted = client.post(
            "/v1/agent-marketplace/listings", json={"agent_card_id": "card-1", "submitted_by": "alice"}, headers=headers,
        ).json()

        # Not yet published -- doesn't show up in the default (published-only) search.
        pre_approval = client.get("/v1/agent-marketplace/listings", params={"tenant_id": "acme"}, headers=headers).json()
        assert pre_approval["total"] == 0

        approved = client.post(
            f"/v1/agent-marketplace/listings/{submitted['id']}/approve", json={"reviewed_by": "bob"}, headers=headers,
        ).json()
        assert approved["status"] == "published"

        post_approval = client.get("/v1/agent-marketplace/listings", params={"tenant_id": "acme"}, headers=headers).json()
        assert post_approval["total"] == 1

        usage = client.post(
            f"/v1/agent-marketplace/listings/{submitted['id']}/record-usage",
            json={"consumer_tenant_id": "globex"}, headers=headers,
        )

    assert usage.status_code == 200
    assert usage.json()["reuse_count"] == 1


def test_approving_an_already_published_listing_returns_409():
    repository = InMemoryAgentMarketplaceRepository()
    app = _app(repository)
    headers = {"Authorization": f"Bearer {_token()}"}

    with TestClient(app) as client:
        submitted = client.post(
            "/v1/agent-marketplace/listings", json={"agent_card_id": "card-1"}, headers=headers,
        ).json()
        client.post(f"/v1/agent-marketplace/listings/{submitted['id']}/approve", json={}, headers=headers)

        resp = client.post(f"/v1/agent-marketplace/listings/{submitted['id']}/approve", json={}, headers=headers)

    assert resp.status_code == 409
