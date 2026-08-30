"""Dependency-stub service for Secrets and Credential Management.

Stands in for this module's two real platform-peer dependencies --
Identity and Access (Module 31) and Auditability (Module 20) -- so the
Secret Access Service's zero-trust-gated retrieval path is exercised end
to end without either peer itself deployed alongside it, per the LLD's
Deployability and Testability Contract. Encryption at rest needs no
external peer -- it's pure, deterministic cryptography.
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Secrets and Credential Management dependency stub")


@app.post("/v1/identity-access/authorize")
async def authorize() -> dict:
    return {"allowed": True, "reason": "ok"}


@app.post("/v1/auditability/events")
async def ingest_event() -> dict:
    return {
        "id": "event-stub", "tenant_id": "default", "source_module": "secrets-and-credential-management",
        "event_type": "secrets.access_attempt", "payload": {}, "sequence_number": 1,
        "entry_hash": "stub", "prev_hash": None, "occurred_at": "2026-01-01T00:00:00Z",
    }


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
