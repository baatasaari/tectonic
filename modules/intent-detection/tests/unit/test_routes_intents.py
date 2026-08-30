"""API-level tests for the FastAPI routes -- currently just the ticket
#82 NUL-byte-in-a-raw-string-query-parameter regression on `GET
/drift-reports`. This module wasn't in the sweep's original module
list -- found by re-grepping the whole platform for the same pattern
once the sweep was otherwise done: `tenant_id` there is a plain,
un-wrapped `str` function parameter rather than an explicit `Query()`
default. No route-level test file existed for this module before;
comprehensive route coverage is a real, separately-scoped gap (see this
module's own README), not one this fix expands.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from intent_detection.api.deps import get_ctx, get_repository
from intent_detection.api.routes_intents import router
from intent_detection.app_context import AppContext
from intent_detection.config import IntentDetectionSettings
from intent_detection.core.compositional_decomposer import CompositionalDecomposer
from intent_detection.core.drift_monitor import DriftMonitor
from intent_detection.core.fakes import InMemoryIntentRepository, StubLLMGatewayClient
from intent_detection.core.primary_classifier import PrimaryClassifier
from intent_detection.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="intent-detection", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=IntentDetectionSettings(), engine=None, session_factory=None, llm_gateway=StubLLMGatewayClient(),
        primary_classifier=PrimaryClassifier(), decomposer=CompositionalDecomposer(), drift_monitor=DriftMonitor(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="conversational-engine", audience="intent-detection", shared_secret=SECRET)


def _headers():
    return {"Authorization": f"Bearer {_token()}"}


def test_list_drift_reports_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    """Ticket #82: a raw string query parameter never runs through a
    Pydantic body field's own NUL-byte validator, so this reached the
    repository (and, against real Postgres, the database itself) raw
    instead of a clean 422."""
    app = _app(InMemoryIntentRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/intent-detection/drift-reports", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422
