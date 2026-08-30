"""API-level tests for the FastAPI routes -- currently just the ticket
#82 NUL-byte-in-a-raw-string-query-parameter regression on `GET
/scores`. This module wasn't in the sweep's original module list --
found by re-grepping the whole platform for the same pattern once the
sweep was otherwise done: unlike its siblings, its vulnerable
parameters were plain, un-wrapped `str` function parameters rather than
an explicit `Query()` default. No route-level test file existed for
this module before; comprehensive route coverage is a real,
separately-scoped gap (see this module's own README), not one this fix
expands.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from evaluation_framework.api.deps import get_ctx, get_repository
from evaluation_framework.api.routes_evalfw import router
from evaluation_framework.app_context import AppContext
from evaluation_framework.config import EvaluationFrameworkSettings
from evaluation_framework.core.fakes import (
    InMemoryEvaluationFrameworkRepository,
    StubLLMGatewayClient,
)
from evaluation_framework.core.sampler import ProductionSampler
from evaluation_framework.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="evaluation-framework", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=EvaluationFrameworkSettings(), engine=None, session_factory=None,
        llm_gateway=StubLLMGatewayClient(), sampler=ProductionSampler(sample_rate=0.0),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="workflow-engine", audience="evaluation-framework", shared_secret=SECRET)


def _headers():
    return {"Authorization": f"Bearer {_token()}"}


def test_list_scores_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    """Ticket #82: a raw string query parameter never runs through a
    Pydantic body field's own NUL-byte validator, so this reached the
    repository (and, against real Postgres, the database itself) raw
    instead of a clean 422."""
    app = _app(InMemoryEvaluationFrameworkRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/evaluation-framework/scores", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_list_scores_rejects_a_null_byte_in_agent_ref_with_a_clean_422():
    app = _app(InMemoryEvaluationFrameworkRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/evaluation-framework/scores",
            params={"tenant_id": "acme", "agent_ref": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422
