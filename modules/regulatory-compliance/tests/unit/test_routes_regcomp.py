"""API-level tests for the FastAPI routes -- currently just the ticket
#82 NUL-byte-in-a-raw-Query()-parameter regression across the routes
taking a free-text filter. No route-level test file existed for this
module before; comprehensive route coverage is a real, separately-scoped
gap (see this module's own README), not one this fix expands.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from regulatory_compliance.api.deps import get_ctx, get_repository
from regulatory_compliance.api.routes_regcomp import router
from regulatory_compliance.app_context import AppContext
from regulatory_compliance.config import RegulatoryComplianceSettings
from regulatory_compliance.core.fakes import (
    InMemoryRegulatoryComplianceRepository,
    StubAuditabilityClient,
)
from regulatory_compliance.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="regulatory-compliance", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=RegulatoryComplianceSettings(), engine=None, session_factory=None,
        auditability=StubAuditabilityClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="human-oversight", audience="regulatory-compliance", shared_secret=SECRET)


def _headers():
    return {"Authorization": f"Bearer {_token()}"}


def test_list_mappings_rejects_a_null_byte_in_control_name_with_a_clean_422():
    """Ticket #82: a raw `Query()` string never runs through a Pydantic
    body field's own NUL-byte validator, so this reached the repository
    (and, against real Postgres, the database itself) raw instead of a
    clean 422."""
    app = _app(InMemoryRegulatoryComplianceRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/regulatory-compliance/mappings", params={"control_name": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_coverage_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    app = _app(InMemoryRegulatoryComplianceRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/regulatory-compliance/coverage",
            params={"tenant_id": "a\x00b", "framework_name": "soc2"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_get_evidence_pack_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    app = _app(InMemoryRegulatoryComplianceRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/regulatory-compliance/evidence-packs/some-pack", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422
