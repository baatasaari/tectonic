"""Dependency-stub service for Regulatory and Compliance.

Stands in for Auditability (Module 20, not yet built in this platform) —
the LLD's Deployability and Testability Contract: "Runs and tests fully
with Auditability stubbed to return canned evidence data."
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Regulatory and Compliance dependency stub")


@app.get("/v1/auditability/events")
async def query_events(tenant_id: str, control_name: str) -> dict:
    return {
        "events": [
            {
                "tenant_id": tenant_id, "control_name": control_name, "event": "control_implemented",
                "detail": "canned evidence from the dependency stub",
            }
        ]
    }


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
