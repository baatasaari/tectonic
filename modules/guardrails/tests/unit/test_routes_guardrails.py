"""API-level tests for the FastAPI routes -- currently just the ticket
#82 NUL-byte-in-a-raw-Query()-parameter regression on `GET
/red-team-runs` and the sibling invalid-enum-in-a-body-field regression
on `POST /check`'s `stage`. No route-level test file existed for this
module before; comprehensive route coverage is a real, separately-scoped
gap (see this module's own README), not one this fix expands.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from guardrails.api.deps import get_ctx, get_repository
from guardrails.api.routes_guardrails import router
from guardrails.app_context import AppContext
from guardrails.config import GuardrailsSettings
from guardrails.core.fakes import (
    InMemoryGuardrailsRepository,
    StubLLMGatewayClient,
    StubSentinelAgentsClient,
)
from guardrails.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="guardrails", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=GuardrailsSettings(), engine=None, session_factory=None,
        llm_gateway=StubLLMGatewayClient(), sentinel_agents=StubSentinelAgentsClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="conversational-engine", audience="guardrails", shared_secret=SECRET)


def _headers():
    return {"Authorization": f"Bearer {_token()}"}


def test_list_red_team_runs_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    """Ticket #82: a raw `Query()` string never runs through a Pydantic
    body field's own NUL-byte validator, so this reached the repository
    (and, against real Postgres, the database itself) raw instead of a
    clean 422."""
    app = _app(InMemoryGuardrailsRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/guardrails/red-team-runs", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_check_rejects_a_stage_that_is_not_a_real_check_stage():
    """`stage` used to be a bare `str` hand-converted to `CheckStage`
    twice in the route body, raising an unhandled `ValueError` (500) for
    any non-member string -- now typed `CheckStage` directly on
    `CheckRequest` so FastAPI/Pydantic rejects it with a clean 422."""
    app = _app(InMemoryGuardrailsRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/guardrails/check", json={"text": "hello", "stage": "not-a-real-stage"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_check_accepts_a_real_stage():
    app = _app(InMemoryGuardrailsRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/guardrails/check", json={"text": "hello there", "stage": "input"}, headers=_headers(),
        )

    assert resp.status_code == 200
