"""Dependency-stub service for Identity and Access.

Stands in for this module's one real platform-peer dependency --
Auditability (Module 20) -- so the Authorization Service's denial-
emission path is exercised end to end without Auditability itself
deployed alongside it, per the LLD's Deployability and Testability
Contract.
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Identity and Access dependency stub")


@app.post("/v1/auditability/events")
async def ingest_event() -> dict:
    return {
        "id": "event-stub", "tenant_id": "default", "source_module": "identity-access",
        "event_type": "identity_access.unauthorized_attempt", "payload": {}, "sequence_number": 1,
        "entry_hash": "stub", "prev_hash": None, "occurred_at": "2026-01-01T00:00:00Z",
    }


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
