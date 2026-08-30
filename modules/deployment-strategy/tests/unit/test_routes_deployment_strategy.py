"""API-level tests for the FastAPI routes -- tenant resolution from the
X-Tenant-Id header, the full deploy -> promote -> active-deployment
flow, and the canary-health-check-failure 409 through a real app.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from deployment_strategy.api.deps import get_ctx, get_repository
from deployment_strategy.api.routes_deployment_strategy import router
from deployment_strategy.app_context import AppContext
from deployment_strategy.config import DeploymentStrategySettings
from deployment_strategy.core.fakes import (
    InMemoryDeploymentStrategyRepository,
    StubEvaluationFrameworkClient,
    StubFinOpsClient,
)
from deployment_strategy.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET
_PASSING_SCORES = [{"passed": True}] * 5


def _app(repository, *, evaluation_framework=None, finops=None):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="deployment-strategy", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=DeploymentStrategySettings(min_groundedness_sample_size=3, min_health_score=0.8),
        engine=None, session_factory=None,
        evaluation_framework=evaluation_framework or StubEvaluationFrameworkClient(),
        finops=finops or StubFinOpsClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="ci", audience="deployment-strategy", shared_secret=SECRET)


def test_deploy_uses_the_x_tenant_id_header():
    app = _app(InMemoryDeploymentStrategyRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/deployment-strategy/deployments",
            json={"service_name": "conversational-engine", "build_ref": "v1", "target": "prod"},
            headers={"Authorization": f"Bearer {_token()}", "X-Tenant-Id": "acme"},
        )

    assert resp.status_code == 201
    assert resp.json()["tenant_id"] == "acme"
    assert resp.json()["stage"] == "canary"


def test_deploy_without_a_bearer_token_is_rejected():
    app = _app(InMemoryDeploymentStrategyRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/deployment-strategy/deployments",
            json={"service_name": "svc", "build_ref": "v1", "target": "prod"},
        )

    assert resp.status_code == 401


def test_promote_returns_409_when_the_health_check_fails():
    evalfw = StubEvaluationFrameworkClient(scores=[])
    app = _app(InMemoryDeploymentStrategyRepository(), evaluation_framework=evalfw)
    headers = {"Authorization": f"Bearer {_token()}"}

    with TestClient(app) as client:
        deployment = client.post(
            "/v1/deployment-strategy/deployments",
            json={"service_name": "svc", "build_ref": "v1", "target": "prod"}, headers=headers,
        ).json()

        resp = client.post(f"/v1/deployment-strategy/deployments/{deployment['id']}/promote", headers=headers)

    assert resp.status_code == 409


def test_full_deploy_promote_active_deployment_flow():
    evalfw = StubEvaluationFrameworkClient(scores=_PASSING_SCORES)
    app = _app(InMemoryDeploymentStrategyRepository(), evaluation_framework=evalfw)
    headers = {"Authorization": f"Bearer {_token()}", "X-Tenant-Id": "acme"}

    with TestClient(app) as client:
        deployment = client.post(
            "/v1/deployment-strategy/deployments",
            json={"service_name": "conversational-engine", "build_ref": "v1", "target": "prod"}, headers=headers,
        ).json()

        health = client.get(f"/v1/deployment-strategy/deployments/{deployment['id']}/canary-health", headers=headers).json()
        assert health["passed"] is True

        promoted = client.post(f"/v1/deployment-strategy/deployments/{deployment['id']}/promote", headers=headers).json()
        assert promoted["stage"] == "active"

        active = client.get(
            "/v1/deployment-strategy/services/conversational-engine/active", params={"target": "prod"}, headers=headers,
        ).json()

    assert active["id"] == deployment["id"]


def test_active_deployment_returns_404_when_nothing_is_active():
    app = _app(InMemoryDeploymentStrategyRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/deployment-strategy/services/svc/active", params={"target": "prod"},
            headers={"Authorization": f"Bearer {_token()}"},
        )

    assert resp.status_code == 404


def test_rollback_records_the_reason():
    app = _app(InMemoryDeploymentStrategyRepository())
    headers = {"Authorization": f"Bearer {_token()}"}

    with TestClient(app) as client:
        deployment = client.post(
            "/v1/deployment-strategy/deployments",
            json={"service_name": "svc", "build_ref": "v1", "target": "prod"}, headers=headers,
        ).json()

        resp = client.post(
            f"/v1/deployment-strategy/deployments/{deployment['id']}/rollback",
            json={"reason": "regression"}, headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["stage"] == "rolled_back"
    assert resp.json()["rollback_reason"] == "regression"


def test_list_deployments_rejects_a_null_byte_in_a_query_param_with_a_clean_422():
    """Ticket #82: a raw `Query()` string never runs through a Pydantic
    body field's own NUL-byte validator, so this reached the repository
    (and, against real Postgres, the database itself) raw instead of a
    clean 422."""
    app = _app(InMemoryDeploymentStrategyRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/deployment-strategy/deployments", params={"service_name": "a\x00b"},
            headers={"Authorization": f"Bearer {_token()}"},
        )

    assert resp.status_code == 422
