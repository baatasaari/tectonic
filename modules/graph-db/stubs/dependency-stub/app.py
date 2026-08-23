"""Dependency-stub service for Graph DB.

Stands in for Auditability (best-effort event publishing on every write).
Per the LLD, this module "has no upstream module dependencies for its own
core operation (write/query), only downstream consumers" — Auditability
is the only outbound call.
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Graph DB dependency stub")


class AuditEvent(BaseModel):
    event: str
    tenant_id: str | None = None


@app.post("/v1/auditability/events")
async def auditability_events(body: dict) -> dict:
    return {"status": "ok"}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
