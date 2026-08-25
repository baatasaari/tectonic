"""API-level tests for the FastAPI routes -- tenant resolution from the
X-Tenant-Id header, extraction across modalities, and the groundedness
gate through a real app.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from multi_modality.api.deps import get_ctx, get_repository
from multi_modality.api.routes_multi_modality import router
from multi_modality.app_context import AppContext
from multi_modality.config import MultiModalitySettings
from multi_modality.core.fakes import InMemoryMultiModalityRepository, StubGuardrailsClient
from multi_modality.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository, *, guardrails=None):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="multi-modality", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=MultiModalitySettings(), engine=None, session_factory=None,
        guardrails=guardrails or StubGuardrailsClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="conversational-engine", audience="multi-modality", shared_secret=SECRET)


def _headers(**extra):
    return {"Authorization": f"Bearer {_token()}", **extra}


def test_extract_uses_the_x_tenant_id_header():
    app = _app(InMemoryMultiModalityRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/multi-modality/extractions",
            json={"modality": "text", "raw_content": "  hello  "},
            headers=_headers(**{"X-Tenant-Id": "acme"}),
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["tenant_id"] == "acme"
    assert body["extracted_content"] == "hello"
    assert body["groundedness_decision"] == "not_checked"


def test_extract_without_a_bearer_token_is_rejected():
    app = _app(InMemoryMultiModalityRepository())

    with TestClient(app) as client:
        resp = client.post("/v1/multi-modality/extractions", json={"modality": "text", "raw_content": "hi"})

    assert resp.status_code == 401


def test_extract_with_an_unknown_modality_returns_422():
    app = _app(InMemoryMultiModalityRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/multi-modality/extractions", json={"modality": "smell", "raw_content": "hi"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_extract_runs_the_groundedness_gate_when_a_grounding_context_is_supplied():
    guardrails = StubGuardrailsClient(decision="block", violation_category="ungrounded")
    app = _app(InMemoryMultiModalityRepository(), guardrails=guardrails)

    with TestClient(app) as client:
        resp = client.post(
            "/v1/multi-modality/extractions",
            json={"modality": "document", "raw_content": "claim summary", "grounding_context": "original claim"},
            headers=_headers(),
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["groundedness_decision"] == "block"
    assert body["groundedness_violation_category"] == "ungrounded"


def test_get_and_list_extractions():
    app = _app(InMemoryMultiModalityRepository())

    with TestClient(app) as client:
        created = client.post(
            "/v1/multi-modality/extractions", json={"modality": "voice", "raw_content": "hello [noise] there"},
            headers=_headers(**{"X-Tenant-Id": "acme"}),
        ).json()

        fetched = client.get(f"/v1/multi-modality/extractions/{created['id']}", headers=_headers()).json()
        listed = client.get(
            "/v1/multi-modality/extractions", params={"tenant_id": "acme"}, headers=_headers(),
        ).json()

    assert fetched["id"] == created["id"]
    assert fetched["extracted_content"] == "hello there"
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == created["id"]


def test_get_extraction_returns_404_when_missing():
    app = _app(InMemoryMultiModalityRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/multi-modality/extractions/does-not-exist", headers=_headers())

    assert resp.status_code == 404
