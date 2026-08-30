"""API-level tests for the FastAPI routes -- tenant resolution from the
X-Tenant-Id header, usage-event ingestion, cost reports, budget-policy
CRUD, and the evaluate/actions endpoints through a real app."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from finops.api.deps import get_ctx, get_repository
from finops.api.routes_finops import router
from finops.app_context import AppContext
from finops.config import FinOpsSettings
from finops.core.fakes import InMemoryFinOpsRepository, StubLLMGatewaySpendClient
from finops.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository, *, llm_gateway=None, settings=None):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="finops", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=settings or FinOpsSettings(), engine=None, session_factory=None,
        llm_gateway=llm_gateway or StubLLMGatewaySpendClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="some-module", audience="finops", shared_secret=SECRET)


def _headers(**extra):
    return {"Authorization": f"Bearer {_token()}", **extra}


def test_report_usage_event_uses_the_x_tenant_id_header():
    app = _app(InMemoryFinOpsRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/finops/usage-events",
            json={"source_module": "vector-db", "resource_type": "storage-gb", "quantity": 10, "unit_cost": 1.5},
            headers=_headers(**{"X-Tenant-Id": "acme"}),
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["tenant_id"] == "acme"
    assert body["cost"] == 15.0


def test_usage_event_ingestion_without_a_bearer_token_is_rejected():
    app = _app(InMemoryFinOpsRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/finops/usage-events",
            json={"source_module": "vector-db", "resource_type": "storage-gb", "quantity": 1, "unit_cost": 1},
        )

    assert resp.status_code == 401


def test_cost_report_combines_llm_gateway_spend_with_ingested_events():
    llm_gateway = StubLLMGatewaySpendClient(spend=25.0)
    app = _app(InMemoryFinOpsRepository(), llm_gateway=llm_gateway)

    with TestClient(app) as client:
        client.post(
            "/v1/finops/usage-events",
            json={"source_module": "vector-db", "resource_type": "storage-gb", "quantity": 5, "unit_cost": 2.0},
            headers=_headers(**{"X-Tenant-Id": "acme"}),
        )
        resp = client.get(
            "/v1/finops/cost-reports/acme", params={"period": "monthly"}, headers=_headers(),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_gateway_spend"] == 25.0
    assert body["other_usage_cost"] == 10.0
    assert body["total_cost"] == 35.0
    assert body["budget_policy"] is None


def test_cost_report_with_an_unknown_budget_policy_id_returns_404():
    app = _app(InMemoryFinOpsRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/finops/cost-reports/acme",
            params={"period": "monthly", "budget_policy_id": "does-not-exist"},
            headers=_headers(),
        )

    assert resp.status_code == 404


def test_create_and_get_budget_policy_round_trip():
    app = _app(InMemoryFinOpsRepository())

    with TestClient(app) as client:
        created = client.post(
            "/v1/finops/budget-policies",
            json={"period": "monthly", "limit_amount": 500.0, "alert_threshold_pct": 0.75},
            headers=_headers(**{"X-Tenant-Id": "acme"}),
        ).json()
        assert created["tenant_id"] == "acme"

        fetched = client.get(f"/v1/finops/budget-policies/{created['id']}", headers=_headers()).json()

    assert fetched["id"] == created["id"]
    assert fetched["limit_amount"] == 500.0


def test_cost_report_rejects_a_period_that_is_not_a_real_budget_period():
    """`period` is now typed `BudgetPeriod` directly, so FastAPI/Pydantic
    itself rejects anything not a real member (a clean 422, a NUL byte
    included) instead of this route hand-parsing it and letting an
    invalid value raise an unhandled ValueError (500)."""
    app = _app(InMemoryFinOpsRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/finops/cost-reports/acme", params={"period": "not-a-real-period"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_cost_report_rejects_a_null_byte_in_budget_policy_id_with_a_clean_422():
    """Ticket #82: a raw `Query()` string never runs through a Pydantic
    body field's own NUL-byte validator, so this reached the repository
    (and, against real Postgres, the database itself) raw instead of a
    clean 422."""
    app = _app(InMemoryFinOpsRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/finops/cost-reports/acme", params={"period": "monthly", "budget_policy_id": "a\x00b"},
            headers=_headers(),
        )

    assert resp.status_code == 422


def test_create_budget_policy_rejects_a_period_that_is_not_a_real_budget_period():
    """Same fix, on the POST /budget-policies body field this time."""
    app = _app(InMemoryFinOpsRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/finops/budget-policies",
            json={"period": "not-a-real-period", "limit_amount": 500.0},
            headers=_headers(**{"X-Tenant-Id": "acme"}),
        )

    assert resp.status_code == 422


def test_get_budget_policy_returns_404_when_missing():
    app = _app(InMemoryFinOpsRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/finops/budget-policies/does-not-exist", headers=_headers())

    assert resp.status_code == 404


def test_evaluate_returns_204_when_no_action_is_warranted():
    app = _app(InMemoryFinOpsRepository(), llm_gateway=StubLLMGatewaySpendClient(spend=1.0))

    with TestClient(app) as client:
        policy = client.post(
            "/v1/finops/budget-policies",
            json={"period": "monthly", "limit_amount": 10000.0},
            headers=_headers(**{"X-Tenant-Id": "acme"}),
        ).json()

        resp = client.post(f"/v1/finops/budget-policies/{policy['id']}/evaluate", headers=_headers())

    assert resp.status_code == 204


def test_evaluate_returns_the_action_and_it_appears_in_the_audit_trail():
    settings = FinOpsSettings(min_alert_threshold_pct=0.5, alert_threshold_step=0.05)
    app = _app(
        InMemoryFinOpsRepository(), llm_gateway=StubLLMGatewaySpendClient(spend=8000.0), settings=settings,
    )

    with TestClient(app) as client:
        policy = client.post(
            "/v1/finops/budget-policies",
            json={"period": "monthly", "limit_amount": 100.0, "alert_threshold_pct": 0.8},
            headers=_headers(**{"X-Tenant-Id": "acme"}),
        ).json()

        resp = client.post(f"/v1/finops/budget-policies/{policy['id']}/evaluate", headers=_headers())
        assert resp.status_code == 200
        action = resp.json()
        assert action["action_type"] == "lowered_alert_threshold"

        actions = client.get(f"/v1/finops/budget-policies/{policy['id']}/actions", headers=_headers()).json()

    assert actions["total"] == 1
    assert actions["items"][0]["id"] == action["id"]
