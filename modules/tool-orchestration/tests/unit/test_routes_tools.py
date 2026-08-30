"""API-level tests for the FastAPI routes -- currently just the ticket
#82 NUL-byte-in-a-raw-string-query-parameter regression on `GET
/tools`. This module wasn't in the sweep's original module list --
found by re-grepping the whole platform for the same pattern once the
sweep was otherwise done: `status` there is a plain, un-wrapped `str`
function parameter rather than an explicit `Query()` default. No
route-level test file existed for this module before; comprehensive
route coverage is a real, separately-scoped gap (see this module's own
README), not one this fix expands.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tool_orchestration.api.deps import get_ctx, get_repository
from tool_orchestration.api.routes_tools import router
from tool_orchestration.app_context import AppContext
from tool_orchestration.config import ToolOrchestrationSettings
from tool_orchestration.core.fakes import (
    FakeMCPClientAdapter,
    InMemoryToolRepository,
    StubGuardrailsClient,
    StubLLMGatewayClient,
    StubSentinelAgentsClient,
)
from tool_orchestration.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="tool-orchestration", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=ToolOrchestrationSettings(), engine=None, session_factory=None, redis=None,
        mcp_client=FakeMCPClientAdapter(), llm_gateway=StubLLMGatewayClient(),
        guardrails=StubGuardrailsClient(), sentinel=StubSentinelAgentsClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="workflow-engine", audience="tool-orchestration", shared_secret=SECRET)


def _headers():
    return {"Authorization": f"Bearer {_token()}"}


def test_list_tools_rejects_a_null_byte_in_status_with_a_clean_422():
    """Ticket #82: a raw string query parameter never runs through a
    Pydantic body field's own NUL-byte validator, so this reached the
    repository (and, against real Postgres, the database itself) raw
    instead of a clean 422."""
    app = _app(InMemoryToolRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/tool-orchestration/tools", params={"status": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422
