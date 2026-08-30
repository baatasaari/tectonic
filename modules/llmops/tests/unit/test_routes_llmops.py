"""API-level tests for the FastAPI routes -- tenant resolution from the
X-Tenant-Id header, the full register -> start-canary -> promote ->
active-version flow, and the canary-gate-failure 409 through a real app.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from llmops.api.deps import get_ctx, get_repository
from llmops.api.routes_llmops import router
from llmops.app_context import AppContext
from llmops.config import LLMOpsSettings
from llmops.core.fakes import InMemoryLLMOpsRepository, StubEvaluationFrameworkClient
from llmops.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET
_PASSING_SCORES = [{"passed": True}] * 5


def _app(repository, *, evaluation_framework=None):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="llmops", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=LLMOpsSettings(min_canary_sample_size=3, min_canary_pass_rate=0.8), engine=None, session_factory=None,
        evaluation_framework=evaluation_framework or StubEvaluationFrameworkClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="workflow-engine", audience="llmops", shared_secret=SECRET)


def test_register_uses_the_x_tenant_id_header():
    app = _app(InMemoryLLMOpsRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/llmops/model-versions", json={"model_name": "chat-default", "version": "1", "artifact_ref": "openai/gpt-x"},
            headers={"Authorization": f"Bearer {_token()}", "X-Tenant-Id": "acme"},
        )

    assert resp.status_code == 201
    assert resp.json()["tenant_id"] == "acme"
    assert resp.json()["status"] == "registered"


def test_register_without_a_bearer_token_is_rejected():
    app = _app(InMemoryLLMOpsRepository())

    with TestClient(app) as client:
        resp = client.post("/v1/llmops/model-versions", json={"model_name": "m", "version": "1", "artifact_ref": "a"})

    assert resp.status_code == 401


def test_promote_returns_409_when_the_canary_gate_fails():
    evalfw = StubEvaluationFrameworkClient(scores=[])
    app = _app(InMemoryLLMOpsRepository(), evaluation_framework=evalfw)
    headers = {"Authorization": f"Bearer {_token()}"}

    with TestClient(app) as client:
        version = client.post(
            "/v1/llmops/model-versions", json={"model_name": "m", "version": "1", "artifact_ref": "a"}, headers=headers,
        ).json()
        deployment = client.post(
            "/v1/llmops/deployments", json={"model_version_id": version["id"], "target": "prod"}, headers=headers,
        ).json()

        resp = client.post(f"/v1/llmops/deployments/{deployment['id']}/promote", headers=headers)

    assert resp.status_code == 409


def test_full_register_canary_promote_active_version_flow():
    evalfw = StubEvaluationFrameworkClient(scores=_PASSING_SCORES)
    app = _app(InMemoryLLMOpsRepository(), evaluation_framework=evalfw)
    headers = {"Authorization": f"Bearer {_token()}", "X-Tenant-Id": "acme"}

    with TestClient(app) as client:
        version = client.post(
            "/v1/llmops/model-versions", json={"model_name": "chat-default", "version": "1", "artifact_ref": "a"},
            headers=headers,
        ).json()
        deployment = client.post(
            "/v1/llmops/deployments", json={"model_version_id": version["id"], "target": "prod"}, headers=headers,
        ).json()

        gate = client.get(f"/v1/llmops/deployments/{deployment['id']}/canary-gate", headers=headers).json()
        assert gate["passed"] is True

        promoted = client.post(f"/v1/llmops/deployments/{deployment['id']}/promote", headers=headers).json()
        assert promoted["stage"] == "active"

        active = client.get(
            "/v1/llmops/models/chat-default/active", params={"target": "prod"}, headers=headers,
        ).json()

    assert active["id"] == version["id"]


def test_active_version_returns_404_when_nothing_is_active():
    app = _app(InMemoryLLMOpsRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/llmops/models/chat-default/active", params={"target": "prod"},
            headers={"Authorization": f"Bearer {_token()}"},
        )

    assert resp.status_code == 404


def test_list_model_versions_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    """Ticket #82: a raw `Query()` string never runs through a Pydantic
    body field's own NUL-byte validator, so this reached the repository
    (and, against real Postgres, the database itself) raw instead of a
    clean 422."""
    app = _app(InMemoryLLMOpsRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/llmops/model-versions", params={"tenant_id": "a\x00b"},
            headers={"Authorization": f"Bearer {_token()}"},
        )

    assert resp.status_code == 422


def test_active_version_rejects_a_null_byte_in_target_with_a_clean_422():
    app = _app(InMemoryLLMOpsRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/llmops/models/chat-default/active", params={"target": "a\x00b"},
            headers={"Authorization": f"Bearer {_token()}"},
        )

    assert resp.status_code == 422
