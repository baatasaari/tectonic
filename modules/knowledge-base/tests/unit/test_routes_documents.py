"""API-level tests for the FastAPI routes -- currently just the ticket
#82 NUL-byte-in-a-raw-Query()-parameter regression and the sibling
invalid-enum-in-a-Form()-field regression. No route-level test file
existed for this module before; comprehensive route coverage is a real,
separately-scoped gap (see this module's own README), not one this fix
expands.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from knowledge_base.api.deps import get_ctx, get_repository
from knowledge_base.api.routes_documents import router
from knowledge_base.app_context import AppContext
from knowledge_base.config import KnowledgeBaseSettings
from knowledge_base.core.fakes import (
    InMemoryBlobStorage,
    InMemoryKnowledgeBaseRepository,
    StubGraphDBClient,
    StubVectorDBClient,
)
from knowledge_base.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="knowledge-base", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=KnowledgeBaseSettings(), engine=None, session_factory=None,
        blob_storage=InMemoryBlobStorage(), vector_db=StubVectorDBClient(), graph_db=StubGraphDBClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="agentic-rag", audience="knowledge-base", shared_secret=SECRET)


def test_list_chunks_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    """Ticket #82: a raw `Query()` string never runs through a Pydantic
    body field's own NUL-byte validator, so this reached the repository
    (and, against real Postgres, the database itself) raw instead of a
    clean 422."""
    app = _app(InMemoryKnowledgeBaseRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/knowledge-base/chunks", params={"policy_tag": "pii", "tenant_id": "a\x00b"},
            headers={"Authorization": f"Bearer {_token()}"},
        )

    assert resp.status_code == 422


def test_ingest_document_rejects_a_source_type_that_is_not_a_real_source_type():
    """`source_type` used to be a bare `str` hand-converted to
    `SourceType`, raising an unhandled `ValueError` (500) for any
    non-member string -- now typed `SourceType` directly so FastAPI/
    Pydantic rejects it with a clean 422."""
    app = _app(InMemoryKnowledgeBaseRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/knowledge-base/documents",
            data={"tenant_id": "acme", "title": "doc", "source_type": "not-a-real-source-type", "content_text": "hi"},
            headers={"Authorization": f"Bearer {_token()}"},
        )

    assert resp.status_code == 422
