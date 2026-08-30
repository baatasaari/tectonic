"""Dependency-stub service for SDK and Developer Portal.

Stands in for this module's four real platform-peer dependencies --
Identity and Access (Module 31), Multi-tenancy (Module 30),
Auditability (Module 20), and (via FastAPI's own auto-generated
`/openapi.json`) a real, live peer spec for the catalogue/SDK
generation path -- so the full register -> sync-catalogue ->
generate-SDK -> adoption-metric path is exercised end to end without
any real peer deployed alongside it, per the LLD's Deployability and
Testability Contract.
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="SDK and Developer Portal dependency stub")


@app.post("/v1/identity-access/identities")
async def register_identity() -> dict:
    return {
        "id": "identity-stub", "tenant_id": "default", "name": "stub", "type": "user", "status": "active",
        "role_names": [], "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
    }


@app.post("/v1/identity-access/identities/{identity_id}/revoke")
async def revoke_identity(identity_id: str) -> dict:
    return {
        "id": identity_id, "tenant_id": "default", "name": "stub", "type": "user", "status": "revoked",
        "role_names": [], "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
    }


@app.post("/v1/identity-access/tokens")
async def issue_token() -> dict:
    return {"token": "stub-token", "granted_scopes": []}


@app.post("/v1/multi-tenancy/tenants")
async def create_tenant() -> dict:
    return {
        "id": "tenant-stub", "name": "sandbox-stub", "status": "active", "tier": "sandbox",
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
    }


@app.get("/v1/auditability/events")
async def list_events() -> dict:
    return {"items": [], "total": 0, "limit": 1, "offset": 0}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
