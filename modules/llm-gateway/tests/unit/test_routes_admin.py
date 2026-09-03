"""API-level tests for `/v1/llm-gateway/admin/*` -- the ticket #82
NUL-byte-in-a-raw-string-query-parameter regression on `GET
/virtual-keys` (`tenant_id` there is a plain, un-wrapped `str` function
parameter rather than an explicit `Query()` default -- why the earlier
platform-wide grep for `Query(` missed this file) and the sibling
NUL-byte-in-a-body-field regressions on `POST /providers`, `POST
/virtual-keys` and `POST /budget-policies` (found by this module's own
OpenAPI contract-test tier). This module wasn't in the sweep's
original module list. No route-level test file existed for this
router before; comprehensive route coverage is a real,
separately-scoped gap (see this module's own README), not one this fix
expands.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from llm_gateway.api.deps import get_repository
from llm_gateway.api.routes_admin import router
from llm_gateway.core.fakes import InMemoryGatewayRepository
from llm_gateway.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="llm-gateway", shared_secret=SECRET)
    app.include_router(router)
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="finops", audience="llm-gateway", shared_secret=SECRET)


def _headers():
    return {"Authorization": f"Bearer {_token()}"}


def test_list_virtual_keys_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    """Ticket #82: a raw string query parameter never runs through a
    Pydantic body field's own NUL-byte validator, so this reached the
    repository (and, against real Postgres, the database itself) raw
    instead of a clean 422."""
    app = _app(InMemoryGatewayRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/llm-gateway/admin/virtual-keys", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_create_provider_config_rejects_a_null_byte_in_endpoint_with_a_clean_422():
    """This module's own OpenAPI contract-test tier found this one: a
    NUL byte in a body field reached the database raw
    (`UntranslatableCharacterError`) instead of a clean 422 -- fixed
    with a `_reject_null_byte` field_validator, the same pattern
    Multi-tenancy's and Billing and Metering's own schemas already
    established."""
    app = _app(InMemoryGatewayRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/llm-gateway/admin/providers",
            json={"provider_name": "openai", "endpoint": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_create_virtual_key_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    app = _app(InMemoryGatewayRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/llm-gateway/admin/virtual-keys",
            json={"tenant_id": "a\x00b", "budget_policy_ref": "does-not-exist"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_create_budget_policy_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    app = _app(InMemoryGatewayRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/llm-gateway/admin/budget-policies",
            json={"tenant_id": "a\x00b", "period": "monthly", "limit_amount": 100.0}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_create_provider_config_rejects_a_priority_past_int4_range_with_a_clean_422():
    """This module's own OpenAPI contract-test tier found this one too:
    `priority` was a bare `int` -- schema-valid per OpenAPI -- but
    `ProviderConfigRecord.priority` is a Postgres `INTEGER` (int4, max
    2_147_483_647); `2**31` reached the database raw and crashed with an
    unhandled `asyncpg.DataError` instead of a clean 422. Fixed with
    `Field(ge=0, le=1_000_000)` on the schema (see `schemas/admin.py`)."""
    app = _app(InMemoryGatewayRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/llm-gateway/admin/providers",
            json={"provider_name": "openai", "endpoint": "https://api.openai.com", "priority": 2_147_483_648},
            headers=_headers(),
        )

    assert resp.status_code == 422
