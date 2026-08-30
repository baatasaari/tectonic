"""API-level tests for the FastAPI routes -- tenant resolution from the
X-Tenant-Id header, the register -> A/B test -> conclude -> active-version
flow, drift-check, and the reflect endpoint through a real app.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from promptops.api.deps import get_ctx, get_repository
from promptops.api.routes_promptops import router
from promptops.app_context import AppContext
from promptops.config import PromptOpsSettings
from promptops.core.ab_testing_service import evaluation_ref
from promptops.core.fakes import (
    InMemoryPromptOpsRepository,
    StubEvaluationFrameworkClient,
    StubLLMGatewayClient,
)
from promptops.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET
_PASSING = [{"passed": True}] * 20
_FAILING = [{"passed": False}] * 20


def _app(repository, *, evaluation_framework=None, llm_gateway=None):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="promptops", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=PromptOpsSettings(
            min_ab_sample_size_per_arm=3, ab_significance_level=0.05,
            min_reflection_sample_size=3, max_pass_rate_before_reflection=0.9,
        ),
        engine=None, session_factory=None,
        evaluation_framework=evaluation_framework or StubEvaluationFrameworkClient(),
        llm_gateway=llm_gateway or StubLLMGatewayClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="ci", audience="promptops", shared_secret=SECRET)


def _headers(**extra):
    return {"Authorization": f"Bearer {_token()}", **extra}


def test_register_uses_the_x_tenant_id_header():
    app = _app(InMemoryPromptOpsRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/promptops/prompt-versions",
            json={"prompt_name": "claims-summariser", "version": "1", "template": "Summarise: {input}"},
            headers=_headers(**{"X-Tenant-Id": "acme"}),
        )

    assert resp.status_code == 201
    assert resp.json()["tenant_id"] == "acme"
    assert resp.json()["status"] == "draft"


def test_register_without_a_bearer_token_is_rejected():
    app = _app(InMemoryPromptOpsRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/promptops/prompt-versions", json={"prompt_name": "p", "version": "1", "template": "t"},
        )

    assert resp.status_code == 401


def test_conclude_returns_409_when_not_significant():
    same_scores = [{"passed": True}] * 6 + [{"passed": False}] * 4
    a_ref, b_ref = evaluation_ref("p", "1"), evaluation_ref("p", "2")
    evalfw = StubEvaluationFrameworkClient(scores_by_ref={a_ref: same_scores, b_ref: same_scores})
    app = _app(InMemoryPromptOpsRepository(), evaluation_framework=evalfw)
    headers = _headers()

    with TestClient(app) as client:
        a = client.post(
            "/v1/promptops/prompt-versions", json={"prompt_name": "p", "version": "1", "template": "t"}, headers=headers,
        ).json()
        b = client.post(
            "/v1/promptops/prompt-versions", json={"prompt_name": "p", "version": "2", "template": "t"}, headers=headers,
        ).json()
        ab_test = client.post(
            "/v1/promptops/ab-tests",
            json={"prompt_name": "p", "version_a_id": a["id"], "version_b_id": b["id"]}, headers=headers,
        ).json()

        resp = client.post(f"/v1/promptops/ab-tests/{ab_test['id']}/conclude", headers=headers)

    assert resp.status_code == 409


def test_full_register_ab_test_conclude_active_flow():
    a_ref, b_ref = evaluation_ref("claims-summariser", "1"), evaluation_ref("claims-summariser", "2")
    evalfw = StubEvaluationFrameworkClient(scores_by_ref={a_ref: _PASSING, b_ref: _FAILING})
    app = _app(InMemoryPromptOpsRepository(), evaluation_framework=evalfw)
    headers = _headers(**{"X-Tenant-Id": "acme"})

    with TestClient(app) as client:
        a = client.post(
            "/v1/promptops/prompt-versions", json={"prompt_name": "claims-summariser", "version": "1", "template": "t1"},
            headers=headers,
        ).json()
        b = client.post(
            "/v1/promptops/prompt-versions", json={"prompt_name": "claims-summariser", "version": "2", "template": "t2"},
            headers=headers,
        ).json()
        ab_test = client.post(
            "/v1/promptops/ab-tests",
            json={"prompt_name": "claims-summariser", "version_a_id": a["id"], "version_b_id": b["id"]}, headers=headers,
        ).json()

        result = client.get(f"/v1/promptops/ab-tests/{ab_test['id']}/result", headers=headers).json()
        assert result["significant"] is True
        assert result["winner_version_id"] == a["id"]

        concluded = client.post(f"/v1/promptops/ab-tests/{ab_test['id']}/conclude", headers=headers).json()
        assert concluded["status"] == "concluded"

        active = client.get(
            "/v1/promptops/prompts/claims-summariser/active", headers=headers,
        ).json()

    assert active["id"] == a["id"]


def test_active_version_returns_404_when_nothing_is_active():
    app = _app(InMemoryPromptOpsRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/promptops/prompts/claims-summariser/active", headers=_headers())

    assert resp.status_code == 404


def test_reflect_returns_204_when_no_optimisation_is_warranted():
    evalfw = StubEvaluationFrameworkClient(scores=[])
    app = _app(InMemoryPromptOpsRepository(), evaluation_framework=evalfw)
    headers = _headers()

    with TestClient(app) as client:
        version = client.post(
            "/v1/promptops/prompt-versions", json={"prompt_name": "p", "version": "1", "template": "t"}, headers=headers,
        ).json()

        resp = client.post(f"/v1/promptops/prompt-versions/{version['id']}/reflect", headers=headers)

    assert resp.status_code == 204


def test_reflect_returns_a_new_draft_version():
    ref = evaluation_ref("p", "1")
    failing = [{"metric_name": "groundedness", "score": 0.3, "threshold": 0.8, "passed": False}] * 5
    evalfw = StubEvaluationFrameworkClient(scores_by_ref={ref: failing})
    llm_gateway = StubLLMGatewayClient(response="Improved template.")
    app = _app(InMemoryPromptOpsRepository(), evaluation_framework=evalfw, llm_gateway=llm_gateway)
    headers = _headers()

    with TestClient(app) as client:
        version = client.post(
            "/v1/promptops/prompt-versions", json={"prompt_name": "p", "version": "1", "template": "original"},
            headers=headers,
        ).json()

        resp = client.post(f"/v1/promptops/prompt-versions/{version['id']}/reflect", headers=headers)

    assert resp.status_code == 201
    body = resp.json()
    assert body["parent_version_id"] == version["id"]
    assert body["template"] == "Improved template."
    assert body["status"] == "draft"


def test_drift_check_endpoint():
    app = _app(InMemoryPromptOpsRepository())
    headers = _headers()

    with TestClient(app) as client:
        version = client.post(
            "/v1/promptops/prompt-versions", json={"prompt_name": "p", "version": "1", "template": "t"}, headers=headers,
        ).json()

        resp = client.get(f"/v1/promptops/prompt-versions/{version['id']}/drift-check", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["drifted"] is False


def test_list_prompt_versions_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    """Ticket #82: a raw `Query()` string never runs through a Pydantic
    body field's own NUL-byte validator, so this reached the repository
    (and, against real Postgres, the database itself) raw instead of a
    clean 422."""
    app = _app(InMemoryPromptOpsRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/promptops/prompt-versions", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422
