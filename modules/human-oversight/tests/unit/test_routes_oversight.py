"""API-level tests for the FastAPI routes -- currently just the ticket
#82 NUL-byte-in-a-raw-Query()-parameter regression on GET
/v1/human-oversight/requests. No route-level test file existed for this
module before; comprehensive route coverage is a real, separately-scoped
gap (see this module's own README), not one this fix expands.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from human_oversight.api.deps import get_ctx, get_repository
from human_oversight.api.routes_oversight import router
from human_oversight.app_context import AppContext
from human_oversight.config import HumanOversightSettings
from human_oversight.core.fakes import (
    InMemoryHumanOversightRepository,
    StubAuditabilityClient,
    StubDecisionCallbackDispatcher,
)
from human_oversight.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="human-oversight", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=HumanOversightSettings(), engine=None, session_factory=None, notification_channels={},
        callback_dispatcher=StubDecisionCallbackDispatcher(), auditability=StubAuditabilityClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="sentinel-agents", audience="human-oversight", shared_secret=SECRET)


def test_list_requests_rejects_a_null_byte_in_a_query_param_with_a_clean_422():
    """Ticket #82: a raw `Query()` string never runs through a Pydantic
    body field's own NUL-byte validator, so this reached the repository
    (and, against real Postgres, the database itself) raw instead of a
    clean 422."""
    app = _app(InMemoryHumanOversightRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/human-oversight/requests", params={"tenant_id": "a\x00b"},
            headers={"Authorization": f"Bearer {_token()}"},
        )

    assert resp.status_code == 422
