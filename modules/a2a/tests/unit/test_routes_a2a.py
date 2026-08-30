"""API-level tests for the FastAPI routes -- tenant resolution from the
X-Tenant-Id header (this platform's standard convention), the outbound
/delegate wrapper, and the full inbound register-policy -> rpc flow
through a real app.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from a2a_gateway.api.deps import get_ctx, get_repository
from a2a_gateway.api.routes_a2a import router
from a2a_gateway.app_context import AppContext
from a2a_gateway.config import A2AGatewaySettings
from a2a_gateway.core.fakes import (
    InMemoryA2AGatewayRepository,
    StubA2APeerClient,
    StubWorkflowEngineClient,
)
from a2a_gateway.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository, *, peer_client=None, workflow_client=None, skill_definition_map=None):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="a2a", shared_secret=SECRET)
    app.include_router(router)

    settings = A2AGatewaySettings(skill_definition_map=skill_definition_map or {"summarize": "def-summarize"})
    ctx = AppContext(
        settings=settings, engine=None, session_factory=None,
        peer_client=peer_client or StubA2APeerClient(), workflow_client=workflow_client or StubWorkflowEngineClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="workflow-engine", audience="a2a", shared_secret=SECRET)


def test_delegate_uses_the_x_tenant_id_header():
    peer = StubA2APeerClient(
        card={"name": "peer", "description": "", "url": "http://peer", "skills": [{"id": "summarize", "name": "Summarize"}]},
    )
    app = _app(InMemoryA2AGatewayRepository(), peer_client=peer)

    with TestClient(app) as client:
        resp = client.post(
            "/v1/a2a/delegate", json={"target_agent_url": "http://peer", "skill_id": "summarize", "input_message": {}},
            headers={"Authorization": f"Bearer {_token()}", "X-Tenant-Id": "acme"},
        )

    assert resp.status_code == 201
    assert resp.json()["tenant_id"] == "acme"


def test_delegate_without_a_bearer_token_is_rejected():
    app = _app(InMemoryA2AGatewayRepository())

    with TestClient(app) as client:
        resp = client.post("/v1/a2a/delegate", json={"target_agent_url": "http://peer", "skill_id": "s", "input_message": {}})

    assert resp.status_code == 401


def test_delegate_returns_422_when_the_target_does_not_advertise_the_skill():
    peer = StubA2APeerClient(card={"name": "peer", "description": "", "url": "http://peer", "skills": []})
    app = _app(InMemoryA2AGatewayRepository(), peer_client=peer)

    with TestClient(app) as client:
        resp = client.post(
            "/v1/a2a/delegate", json={"target_agent_url": "http://peer", "skill_id": "summarize", "input_message": {}},
            headers={"Authorization": f"Bearer {_token()}"},
        )

    assert resp.status_code == 422


def test_get_task_returns_404_for_an_unknown_id():
    app = _app(InMemoryA2AGatewayRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/a2a/tasks/does-not-exist", headers={"Authorization": f"Bearer {_token()}"})

    assert resp.status_code == 404


def test_rpc_is_reachable_without_a_bearer_token():
    """The /rpc surface is deliberately excluded from the platform's shared-secret JWT --
    external agents were never issued it."""
    repository = InMemoryA2AGatewayRepository()
    app = _app(repository)

    with TestClient(app) as client:
        resp = client.post(
            "/v1/a2a/rpc", json={"jsonrpc": "2.0", "method": "message/send", "id": 1, "params": {"skill_id": "summarize", "message": {}}},
            headers={"X-Tenant-Id": "acme", "X-A2A-Caller-Id": "peer-1", "X-A2A-Caller-Url": "http://peer"},
        )

    assert resp.status_code == 200
    # No access policy registered yet -- a JSON-RPC-shaped denial, not an HTTP error.
    assert resp.json()["error"]["code"] == -32001


def test_full_access_policy_then_rpc_flow():
    repository = InMemoryA2AGatewayRepository()
    app = _app(repository)
    headers = {"Authorization": f"Bearer {_token()}", "X-Tenant-Id": "acme"}

    with TestClient(app) as client:
        client.put("/v1/a2a/access-policies/peer-1", json={"allowed_skills": None}, headers=headers)

        resp = client.post(
            "/v1/a2a/rpc", json={"jsonrpc": "2.0", "method": "message/send", "id": 1, "params": {"skill_id": "summarize", "message": {}}},
            headers={"X-Tenant-Id": "acme", "X-A2A-Caller-Id": "peer-1", "X-A2A-Caller-Url": "http://peer"},
        )

    assert resp.status_code == 200
    assert resp.json()["error"] is None
    assert resp.json()["result"]["status"] == "working"


def test_list_tasks_returns_a_paginated_envelope():
    peer = StubA2APeerClient(
        card={"name": "peer", "description": "", "url": "http://peer", "skills": [{"id": "summarize", "name": "Summarize"}]},
    )
    app = _app(InMemoryA2AGatewayRepository(), peer_client=peer)
    headers = {"Authorization": f"Bearer {_token()}", "X-Tenant-Id": "acme"}

    with TestClient(app) as client:
        for _ in range(3):
            client.post(
                "/v1/a2a/delegate", json={"target_agent_url": "http://peer", "skill_id": "summarize", "input_message": {}},
                headers=headers,
            )
        resp = client.get("/v1/a2a/tasks", params={"tenant_id": "acme", "limit": 2}, headers=headers)

    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_list_tasks_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    """Ticket #82: a raw `Query()` string never runs through a Pydantic
    body field's own NUL-byte validator, so this reached the repository
    (and, against real Postgres, the database itself) raw instead of a
    clean 422."""
    app = _app(InMemoryA2AGatewayRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/a2a/tasks", params={"tenant_id": "a\x00b"}, headers={"Authorization": f"Bearer {_token()}"},
        )

    assert resp.status_code == 422


def test_list_tasks_rejects_a_direction_that_is_not_a_real_task_direction():
    """`direction` is now typed `TaskDirection | None` directly, so
    FastAPI/Pydantic itself rejects anything not a real member (a clean
    422) instead of this route hand-parsing it and letting an invalid
    value raise an unhandled ValueError (500)."""
    app = _app(InMemoryA2AGatewayRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/a2a/tasks", params={"direction": "sideways"}, headers={"Authorization": f"Bearer {_token()}"},
        )

    assert resp.status_code == 422
