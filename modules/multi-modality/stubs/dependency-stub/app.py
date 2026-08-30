"""Dependency-stub service for Multi-modality.

Stands in for this module's one real platform-peer dependency --
Guardrails (Module 14) -- so the Extraction Service's full
groundedness-gate path is exercised end to end without Guardrails
itself deployed alongside it, per the LLD's Deployability and
Testability Contract. Plays exactly the one real endpoint
`HTTPGuardrailsClient` calls: `POST /v1/guardrails/check`.
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Multi-modality dependency stub")


@app.post("/v1/guardrails/check")
async def check() -> dict:
    # Canned "allow" -- a real Guardrails would actually run its groundedness_check
    # against the supplied context; this stub just proves the wiring, matching this
    # platform's "stub returns canned data, real behavior is exercised by the unit
    # tier's stub clients with controllable decisions" convention.
    return {"decision": "allow", "violation_category": None, "redacted_text": None, "checks_run": ["groundedness_check"]}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

@app.get("/v1/multi-tenancy/tenants/{tenant_id}/gate")
async def gate(tenant_id: str, module: str | None = None) -> dict:
    return {"allowed": True, "reason": "active"}
