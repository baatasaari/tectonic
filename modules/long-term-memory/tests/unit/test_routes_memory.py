"""API-level tests for the FastAPI routes -- currently just the ticket
#82 NUL-byte-in-a-raw-string-query-parameter regression on `GET
/reflections`. This module wasn't in the sweep's original module list
-- found by re-grepping the whole platform for the same pattern once
the sweep was otherwise done: `agent_ref` there is a plain, un-wrapped
`str` function parameter rather than an explicit `Query()` default. No
route-level test file existed for this module before; comprehensive
route coverage is a real, separately-scoped gap (see this module's own
README), not one this fix expands.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from long_term_memory.api.deps import get_ctx, get_repository
from long_term_memory.api.routes_memory import router
from long_term_memory.app_context import AppContext
from long_term_memory.config import LongTermMemorySettings
from long_term_memory.core.fakes import (
    InMemoryLongTermMemoryRepository,
    StubGraphDBClient,
    StubGuardrailsClient,
    StubLLMGatewayClient,
    StubVectorDBClient,
)
from long_term_memory.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="long-term-memory", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=LongTermMemorySettings(), engine=None, session_factory=None,
        vector_db=StubVectorDBClient(), graph_db=StubGraphDBClient(),
        llm_gateway=StubLLMGatewayClient(), guardrails=StubGuardrailsClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="evaluation-framework", audience="long-term-memory", shared_secret=SECRET)


def _headers():
    return {"Authorization": f"Bearer {_token()}"}


def test_list_reflections_rejects_a_null_byte_in_agent_ref_with_a_clean_422():
    """Ticket #82: a raw string query parameter never runs through a
    Pydantic body field's own NUL-byte validator, so this reached the
    repository (and, against real Postgres, the database itself) raw
    instead of a clean 422."""
    app = _app(InMemoryLongTermMemoryRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/long-term-memory/reflections", params={"agent_ref": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422
