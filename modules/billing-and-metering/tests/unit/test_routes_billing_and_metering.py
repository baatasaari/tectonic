"""API-level tests for the FastAPI routes -- pricing plans, invoice
generation (through a real app, real FinOps/Auditability stubs), and
the draft -> finalize lifecycle.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from billing_and_metering.api.deps import get_ctx, get_repository
from billing_and_metering.api.routes_billing_and_metering import router
from billing_and_metering.app_context import AppContext
from billing_and_metering.config import BillingAndMeteringSettings
from billing_and_metering.core.fakes import (
    InMemoryBillingRepository,
    StubAuditabilityClient,
    StubFinOpsClient,
    StubMultiTenancyClient,
)
from billing_and_metering.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET
AUDIENCE = "billing-and-metering"


def _app(repository, *, finops=None, auditability=None, multi_tenancy=None):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience=AUDIENCE, shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=BillingAndMeteringSettings(), engine=None, session_factory=None,
        finops=finops or StubFinOpsClient(total_cost=100.0),
        auditability=auditability or StubAuditabilityClient(count=10),
        multi_tenancy=multi_tenancy or StubMultiTenancyClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="conversational-engine", audience=AUDIENCE, shared_secret=SECRET)


def _headers(**extra):
    return {"Authorization": f"Bearer {_token()}", **extra}


def test_create_and_get_pricing_plan():
    app = _app(InMemoryBillingRepository())

    with TestClient(app) as client:
        created = client.post(
            "/v1/billing/pricing-plans",
            json={"tenant_id": "acme", "name": "Standard", "unit_prices": {"llm.cost_usd": 1.0}},
            headers=_headers(),
        ).json()
        assert created["unit_prices"] == {"llm.cost_usd": 1.0}

        fetched = client.get(f"/v1/billing/pricing-plans/{created['id']}", headers=_headers()).json()

    assert fetched["id"] == created["id"]


def test_without_a_bearer_token_is_rejected():
    app = _app(InMemoryBillingRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/billing/pricing-plans")

    assert resp.status_code == 401


def test_generate_invoice_without_a_plan_returns_404():
    app = _app(InMemoryBillingRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/billing/invoices/generate", json={"tenant_id": "no-plan-tenant", "period": "monthly"},
            headers=_headers(),
        )

    assert resp.status_code == 404


def test_full_generate_and_finalize_flow():
    app = _app(
        InMemoryBillingRepository(), finops=StubFinOpsClient(total_cost=100.0),
        auditability=StubAuditabilityClient(count=20),
    )
    headers = _headers()

    with TestClient(app) as client:
        client.post(
            "/v1/billing/pricing-plans",
            json={"tenant_id": "acme", "name": "Standard", "unit_prices": {"llm.cost_usd": 1.0, "auditability": 0.1}},
            headers=headers,
        )

        generated = client.post(
            "/v1/billing/invoices/generate", json={"tenant_id": "acme", "period": "monthly"}, headers=headers,
        ).json()
        assert generated["invoice"]["status"] == "draft"
        assert generated["invoice"]["complete"] is True
        assert generated["invoice"]["total_amount"] == 100.0 + 2.0
        assert len(generated["lines"]) == 2

        invoice_id = generated["invoice"]["id"]
        finalized = client.post(f"/v1/billing/invoices/{invoice_id}/finalize", headers=headers).json()
        assert finalized["status"] == "finalized"

        again = client.post(f"/v1/billing/invoices/{invoice_id}/finalize", headers=headers)

    assert again.status_code == 409


def test_get_invoice_returns_404_when_missing():
    app = _app(InMemoryBillingRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/billing/invoices/does-not-exist", headers=_headers())

    assert resp.status_code == 404


def test_list_invoices_rejects_a_status_that_is_not_a_real_invoice_status():
    """Real bug the contract-test tier caught: `?status=<anything>` used to
    be handed to `InvoiceStatus(status)` by hand inside the route, which
    raised an unhandled `ValueError` (500) for any non-member string
    instead of the clean `422` a bad query parameter should get."""
    app = _app(InMemoryBillingRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/billing/invoices?status=not-a-real-status", headers=_headers())

    assert resp.status_code == 422


def test_creating_a_tenant_plan_syncs_its_modules_to_multi_tenancy():
    multi_tenancy = StubMultiTenancyClient()
    app = _app(InMemoryBillingRepository(), multi_tenancy=multi_tenancy)

    with TestClient(app) as client:
        client.post(
            "/v1/billing/pricing-plans",
            json={
                "tenant_id": "acme", "name": "Standard",
                "unit_prices": {"llm.cost_usd": 1.0, "agent-cards": 49.0, "guardrails": 79.0},
            },
            headers=_headers(),
        )

    assert multi_tenancy.calls == [
        {"tenant_id": "acme", "module_names": ["agent-cards", "guardrails"]},
    ]


def test_creating_the_global_default_plan_does_not_sync_to_multi_tenancy():
    multi_tenancy = StubMultiTenancyClient()
    app = _app(InMemoryBillingRepository(), multi_tenancy=multi_tenancy)

    with TestClient(app) as client:
        client.post(
            "/v1/billing/pricing-plans",
            json={"tenant_id": None, "name": "Default", "unit_prices": {"llm.cost_usd": 1.0}},
            headers=_headers(),
        )

    assert multi_tenancy.calls == []


def test_usage_records_listed_after_generation():
    app = _app(InMemoryBillingRepository())
    headers = _headers()

    with TestClient(app) as client:
        client.post(
            "/v1/billing/pricing-plans",
            json={"tenant_id": "acme", "name": "Standard", "unit_prices": {"llm.cost_usd": 1.0}},
            headers=headers,
        )
        client.post("/v1/billing/invoices/generate", json={"tenant_id": "acme", "period": "monthly"}, headers=headers)

        resp = client.get("/v1/billing/usage-records", params={"tenant_id": "acme"}, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_list_usage_records_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    """Ticket #82: a real CI run of this module's own contract tier found
    this -- `tenant_id`/`period` are raw `Query()` strings, which (unlike
    a Pydantic body field) never run through a NUL-byte validator, so a
    NUL byte reached Postgres raw and 500'd instead of a clean 422."""
    app = _app(InMemoryBillingRepository())

    with TestClient(app) as client:
        resp = client.get("/v1/billing/usage-records", params={"tenant_id": "a\x00b"}, headers=_headers())

    assert resp.status_code == 422
