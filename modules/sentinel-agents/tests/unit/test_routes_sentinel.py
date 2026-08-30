"""API-level tests for the FastAPI routes -- currently just the ticket
#82 NUL-byte-in-a-raw-Query()-parameter regression on `GET /alerts` and
`GET /alerts/{alert_id}`. No route-level test file existed for this
module before; comprehensive route coverage is a real, separately-scoped
gap (see this module's own README), not one this fix expands.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sentinel_agents.api.deps import get_ctx, get_repository
from sentinel_agents.api.routes_sentinel import router
from sentinel_agents.app_context import AppContext
from sentinel_agents.config import SentinelAgentsSettings
from sentinel_agents.core.fakes import (
    InMemorySentinelRepository,
    StubAuditabilityClient,
    StubHumanOversightClient,
    StubToolOrchestrationClient,
    StubWorkflowEngineClient,
)
from sentinel_agents.core.swarm_correlation import SwarmWindowTracker
from sentinel_agents.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="sentinel-agents", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=SentinelAgentsSettings(), engine=None, session_factory=None,
        workflow_engine=StubWorkflowEngineClient(), tool_orchestration=StubToolOrchestrationClient(),
        human_oversight=StubHumanOversightClient(), auditability=StubAuditabilityClient(),
        window_tracker=SwarmWindowTracker(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="tool-orchestration", audience="sentinel-agents", shared_secret=SECRET)


def _headers():
    return {"Authorization": f"Bearer {_token()}"}


def test_list_alerts_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    """Ticket #82: a raw `Query()` string never runs through a Pydantic
    body field's own NUL-byte validator, so this reached the repository
    (and, against real Postgres, the database itself) raw instead of a
    clean 422."""
    app = _app(InMemorySentinelRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/sentinel-agents/alerts", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_get_alert_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    app = _app(InMemorySentinelRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/sentinel-agents/alerts/some-alert", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422
