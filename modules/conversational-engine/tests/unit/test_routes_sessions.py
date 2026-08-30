"""API-level tests for `/v1/conversational-engine/sessions/*` through a
real FastAPI app -- no route-level test file existed for this module
before (every prior test exercised `SessionManager` directly, bypassing
FastAPI entirely). Covers the pre-existing create/get/messages/handoff/
close/resume routes and the new list/export/delete routes added for the
independent architecture assessment's Phase 2 exit bar ("session
list/search/export/delete").
"""
from __future__ import annotations

import fakeredis.aioredis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conversational_engine.api.deps import get_ctx, get_repository
from conversational_engine.api.routes_sessions import router
from conversational_engine.app_context import AppContext
from conversational_engine.config import ConversationalEngineSettings
from conversational_engine.core.fakes import (
    InMemoryAuditabilityClient,
    InMemoryConversationRepository,
    InMemoryObservabilityClient,
    StubGuardrailsClient,
    StubHumanOversightClient,
    StubLLMGatewayClient,
    StubLongTermMemoryClient,
)
from conversational_engine.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository=None):
    repository = repository if repository is not None else InMemoryConversationRepository()
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="conversational-engine", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=ConversationalEngineSettings(), engine=None, session_factory=None,
        redis=fakeredis.aioredis.FakeRedis(), llm_gateway=StubLLMGatewayClient(), guardrails=StubGuardrailsClient(),
        long_term_memory=StubLongTermMemoryClient(), human_oversight=StubHumanOversightClient(),
        observability=InMemoryObservabilityClient(), auditability=InMemoryAuditabilityClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="agentic-rag", audience="conversational-engine", shared_secret=SECRET)


def _headers(**extra):
    return {"Authorization": f"Bearer {_token()}", **extra}


def test_create_and_get_session():
    app = _app()
    with TestClient(app) as client:
        created = client.post(
            "/v1/conversational-engine/sessions", json={"channel": "web"}, headers=_headers(**{"X-Tenant-Id": "acme"}),
        ).json()

        fetched = client.get(f"/v1/conversational-engine/sessions/{created['id']}", headers=_headers()).json()

    assert fetched["id"] == created["id"]
    assert fetched["tenant_id"] == "acme"
    assert fetched["channel"] == "web"
    assert fetched["messages"] == []


def test_create_session_with_an_unknown_channel_returns_422():
    app = _app()
    with TestClient(app) as client:
        resp = client.post("/v1/conversational-engine/sessions", json={"channel": "carrier-pigeon"}, headers=_headers())

    assert resp.status_code == 422


def test_get_session_returns_404_when_missing():
    app = _app()
    with TestClient(app) as client:
        resp = client.get("/v1/conversational-engine/sessions/does-not-exist", headers=_headers())

    assert resp.status_code == 404


def test_send_message_completes_a_turn():
    app = _app()
    headers = _headers(**{"X-Tenant-Id": "acme"})
    with TestClient(app) as client:
        session = client.post("/v1/conversational-engine/sessions", json={"channel": "web"}, headers=headers).json()

        resp = client.post(
            f"/v1/conversational-engine/sessions/{session['id']}/messages",
            json={"content": "What are your hours?"}, headers=headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["refused"] is False
    assert body["outbound_message"]["content"] == "Sure, here's an answer."


def test_close_session():
    app = _app()
    with TestClient(app) as client:
        session = client.post("/v1/conversational-engine/sessions", json={"channel": "web"}, headers=_headers()).json()

        resp = client.post(f"/v1/conversational-engine/sessions/{session['id']}/close", headers=_headers())

    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"


def test_manual_handoff():
    app = _app()
    with TestClient(app) as client:
        session = client.post("/v1/conversational-engine/sessions", json={"channel": "web"}, headers=_headers()).json()

        resp = client.post(
            f"/v1/conversational-engine/sessions/{session['id']}/handoff",
            json={"reason": "customer asked for a human"}, headers=_headers(),
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "handed_off"


def test_resume_returns_409_when_nothing_to_resume():
    app = _app()
    with TestClient(app) as client:
        session = client.post("/v1/conversational-engine/sessions", json={"channel": "web"}, headers=_headers()).json()

        resp = client.post(f"/v1/conversational-engine/sessions/{session['id']}/resume", headers=_headers())

    assert resp.status_code == 409


def test_list_sessions_is_tenant_scoped_and_paginated():
    repository = InMemoryConversationRepository()
    app = _app(repository)
    with TestClient(app) as client:
        for i in range(3):
            client.post(
                "/v1/conversational-engine/sessions", json={"channel": "web"},
                headers=_headers(**{"X-Tenant-Id": "acme"}),
            )
        client.post(
            "/v1/conversational-engine/sessions", json={"channel": "web"},
            headers=_headers(**{"X-Tenant-Id": "other-tenant"}),
        )

        resp = client.get(
            "/v1/conversational-engine/sessions", params={"limit": 2}, headers=_headers(**{"X-Tenant-Id": "acme"}),
        )

    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_list_sessions_filters_by_status_channel_and_user_ref():
    app = _app()
    headers = _headers(**{"X-Tenant-Id": "acme"})
    with TestClient(app) as client:
        client.post(
            "/v1/conversational-engine/sessions", json={"channel": "whatsapp", "user_ref": "user-1"}, headers=headers,
        )
        client.post("/v1/conversational-engine/sessions", json={"channel": "web"}, headers=headers)

        resp = client.get(
            "/v1/conversational-engine/sessions", params={"channel": "whatsapp", "user_ref": "user-1"}, headers=headers,
        )

    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["channel"] == "whatsapp"
    assert body["items"][0]["user_ref"] == "user-1"


def test_list_sessions_rejects_a_null_byte_in_a_filter_with_a_clean_422():
    """Ticket #82's platform-wide sweep pattern, applied to this
    newly-added route: a raw `Query()` string never runs through a
    Pydantic body field's own NUL-byte validator."""
    app = _app()
    with TestClient(app) as client:
        resp = client.get(
            "/v1/conversational-engine/sessions", params={"user_ref": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_export_session_includes_messages_and_handoff_events():
    app = _app()
    headers = _headers(**{"X-Tenant-Id": "acme"})
    with TestClient(app) as client:
        session = client.post("/v1/conversational-engine/sessions", json={"channel": "web"}, headers=headers).json()
        client.post(
            f"/v1/conversational-engine/sessions/{session['id']}/messages",
            json={"content": "hello"}, headers=headers,
        )
        client.post(
            f"/v1/conversational-engine/sessions/{session['id']}/handoff",
            json={"reason": "test"}, headers=headers,
        )

        resp = client.get(f"/v1/conversational-engine/sessions/{session['id']}/export", headers=headers)

    body = resp.json()
    assert resp.status_code == 200
    assert body["session"]["id"] == session["id"]
    assert len(body["session"]["messages"]) == 2  # inbound + outbound
    assert len(body["handoff_events"]) == 1
    assert body["handoff_events"][0]["trigger_reason"] == "explicit"
    assert "exported_at" in body


def test_export_session_returns_404_when_missing():
    app = _app()
    with TestClient(app) as client:
        resp = client.get("/v1/conversational-engine/sessions/does-not-exist/export", headers=_headers())

    assert resp.status_code == 404


def test_delete_session_removes_it():
    repository = InMemoryConversationRepository()
    app = _app(repository)
    with TestClient(app) as client:
        session = client.post("/v1/conversational-engine/sessions", json={"channel": "web"}, headers=_headers()).json()

        delete_resp = client.delete(f"/v1/conversational-engine/sessions/{session['id']}", headers=_headers())
        get_resp = client.get(f"/v1/conversational-engine/sessions/{session['id']}", headers=_headers())

    assert delete_resp.status_code == 204
    assert get_resp.status_code == 404


def test_delete_session_is_idempotent_for_an_already_missing_session():
    app = _app()
    with TestClient(app) as client:
        resp = client.delete("/v1/conversational-engine/sessions/does-not-exist", headers=_headers())

    assert resp.status_code == 204
