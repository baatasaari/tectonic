"""API-level tests for the FastAPI routes -- currently just the ticket
#82 NUL-byte-in-a-raw-Query()-parameter regression (and the sibling
invalid-enum-in-a-Query()-parameter regression) across the several
routes that take a `tenant_id`/free-text filter. No route-level test
file existed for this module before; comprehensive route coverage is a
real, separately-scoped gap (see this module's own README), not one
this fix expands.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from observability.api.deps import get_ctx, get_repository
from observability.api.routes_observability import router
from observability.app_context import AppContext
from observability.config import ObservabilitySettings
from observability.core.fakes import InMemoryObservabilityRepository, StubLLMGatewayClient
from observability.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="observability", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=ObservabilitySettings(), engine=None, session_factory=None, llm_gateway=StubLLMGatewayClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="workflow-engine", audience="observability", shared_secret=SECRET)


def _headers():
    return {"Authorization": f"Bearer {_token()}"}


def test_list_traces_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    """Ticket #82: a raw `Query()` string never runs through a Pydantic
    body field's own NUL-byte validator, so this reached the repository
    (and, against real Postgres, the database itself) raw instead of a
    clean 422."""
    app = _app(InMemoryObservabilityRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/observability/traces", params={"tenant_id": "a\x00b"}, headers=_headers())

    assert resp.status_code == 422


def test_get_trace_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    app = _app(InMemoryObservabilityRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/observability/traces/some-trace", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_reasoning_narrative_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    app = _app(InMemoryObservabilityRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/observability/reasoning-narrative/some-trace", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_cost_attribution_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    app = _app(InMemoryObservabilityRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/observability/cost-attribution/some-trace", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_trace_completeness_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    app = _app(InMemoryObservabilityRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/observability/trace-completeness", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_list_slos_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    app = _app(InMemoryObservabilityRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/observability/slos", params={"tenant_id": "a\x00b"}, headers=_headers())

    assert resp.status_code == 422


def test_list_alert_rules_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    app = _app(InMemoryObservabilityRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/observability/alert-rules", params={"tenant_id": "a\x00b"}, headers=_headers())

    assert resp.status_code == 422


def test_list_alert_events_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    app = _app(InMemoryObservabilityRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/observability/alert-events", params={"tenant_id": "a\x00b"}, headers=_headers())

    assert resp.status_code == 422


def test_list_alert_events_rejects_a_status_that_is_not_a_real_alert_status():
    """`status` used to be a bare `str` hand-converted to `AlertStatus`,
    raising an unhandled `ValueError` (500) for any non-member string --
    now typed `AlertStatus` directly so FastAPI/Pydantic rejects it with
    a clean 422."""
    app = _app(InMemoryObservabilityRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/observability/alert-events", params={"status": "not-a-real-status"}, headers=_headers(),
        )

    assert resp.status_code == 422
