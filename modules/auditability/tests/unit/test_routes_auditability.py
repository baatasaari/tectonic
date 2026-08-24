"""API-level tests proving the one genuinely new wiring this module adds:
`source_module` on an ingested event is resolved from the verified
inbound JWT's `iss` claim, not from the request body -- see
security/jwt_auth.py's module docstring. Everything else here is a normal
routes-through-a-real-app pass, dependency-overriding the repository with
the in-memory fake so no database is needed.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auditability.api.deps import get_ctx, get_repository
from auditability.api.routes_auditability import router
from auditability.app_context import AppContext
from auditability.config import AuditabilitySettings
from auditability.core.fakes import InMemoryAuditabilityRepository, StubLLMGatewayClient
from auditability.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

# AuditabilitySettings.jwt_shared_secret is populated via its env-var validation_alias
# (TECTONIC_JWT_SHARED_SECRET), not the field name -- constructing Settings with a custom
# secret kwarg directly isn't how this field is meant to be set. Using its own default
# here (rather than monkeypatching the env) keeps this test independent of env state.
SECRET = INSECURE_DEFAULT_SECRET


def _app(repository, llm_gateway=None):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="auditability", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=AuditabilitySettings(),
        engine=None, session_factory=None, llm_gateway=llm_gateway or StubLLMGatewayClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token(issuer: str) -> str:
    return mint_service_token(issuer=issuer, audience="auditability", shared_secret=SECRET)


def test_ingest_event_resolves_source_module_from_the_jwt_not_the_body():
    repository = InMemoryAuditabilityRepository()
    app = _app(repository)

    with TestClient(app) as client:
        resp = client.post(
            "/v1/auditability/events",
            json={"tenant_id": "t1", "event_type": "handoff", "source_module": "an-attacker-supplied-value"},
            headers={"Authorization": f"Bearer {_token('workflow-engine')}"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["source_module"] == "workflow-engine"  # from the verified token, not the body field above
    assert body["sequence_number"] == 1


def test_ingest_event_requires_tenant_id():
    app = _app(InMemoryAuditabilityRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/auditability/events", json={"event_type": "x"},
            headers={"Authorization": f"Bearer {_token('workflow-engine')}"},
        )

    assert resp.status_code == 400


def test_ingest_event_without_a_bearer_token_is_rejected():
    app = _app(InMemoryAuditabilityRepository())

    with TestClient(app) as client:
        resp = client.post("/v1/auditability/events", json={"tenant_id": "t1", "event_type": "x"})

    assert resp.status_code == 401


def test_list_events_returns_a_paginated_envelope():
    repository = InMemoryAuditabilityRepository()
    app = _app(repository)
    token = _token("workflow-engine")

    with TestClient(app) as client:
        for i in range(3):
            client.post(
                "/v1/auditability/events", json={"tenant_id": "t1", "event_type": "step", "i": i},
                headers={"Authorization": f"Bearer {token}"},
            )
        resp = client.get(
            "/v1/auditability/events", params={"tenant_id": "t1", "limit": 2},
            headers={"Authorization": f"Bearer {token}"},
        )

    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 3
    assert len(body["items"]) == 2
    # newest first
    assert body["items"][0]["sequence_number"] == 3


def test_verify_chain_route_reports_a_valid_chain():
    repository = InMemoryAuditabilityRepository()
    app = _app(repository)
    token = _token("workflow-engine")

    with TestClient(app) as client:
        client.post(
            "/v1/auditability/events", json={"tenant_id": "t1", "event_type": "a"},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = client.get(
            "/v1/auditability/events/verify-chain", params={"tenant_id": "t1"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"tenant_id": "t1", "valid": True, "verified_count": 1, "break_at_sequence": None}


def test_nl_query_echoes_the_translated_filter():
    repository = InMemoryAuditabilityRepository()
    llm_gateway = StubLLMGatewayClient(proposal={"event_type": "handoff"})
    app = _app(repository, llm_gateway=llm_gateway)
    token = _token("workflow-engine")

    with TestClient(app) as client:
        client.post(
            "/v1/auditability/events", json={"tenant_id": "t1", "event_type": "handoff"},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = client.post(
            "/v1/auditability/query", json={"question": "show handoffs", "tenant_id": "t1"},
            headers={"Authorization": f"Bearer {token}"},
        )

    body = resp.json()
    assert resp.status_code == 200
    assert body["filter_used"]["event_type"] == "handoff"
    assert body["results"]["total"] == 1
