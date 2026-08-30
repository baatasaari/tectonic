"""API-level tests for the FastAPI routes -- currently just the ticket
#82 NUL-byte-in-a-raw-Query()-parameter regression on GET
/nodes/{node_id}/neighbours. No route-level test file existed for this
module before; comprehensive route coverage is a real, separately-scoped
gap (see this module's own README), not one this fix expands.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from graph_db.api.deps import get_ctx, get_repository
from graph_db.api.routes_graph import router
from graph_db.app_context import AppContext
from graph_db.config import GraphDbSettings
from graph_db.core.fakes import InMemoryAuditabilityClient, InMemoryGraphRepository
from graph_db.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="graph-db", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=GraphDbSettings(), engine=None, session_factory=None, auditability=InMemoryAuditabilityClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="agentic-rag", audience="graph-db", shared_secret=SECRET)


def test_get_neighbours_rejects_a_null_byte_in_edge_kind_with_a_clean_422():
    """Ticket #82: a raw `Query()` string never runs through a Pydantic
    body field's own NUL-byte validator, so this reached the graph engine
    (and, against real Postgres, the database itself) raw instead of a
    clean 422."""
    app = _app(InMemoryGraphRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/graph-db/nodes/some-node/neighbours", params={"edge_kind": "a\x00b"},
            headers={"Authorization": f"Bearer {_token()}"},
        )

    assert resp.status_code == 422
