"""Dependency-stub service for Sentinel Agents.

Stands in for the intervention/escalation targets named in the LLD's
Deployability and Testability Contract: "Workflow Engine/Tool
Orchestration intervention endpoints stubbed."
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Sentinel Agents dependency stub")


@app.post("/v1/workflow-engine/instances/{instance_id}/pause")
async def pause(instance_id: str) -> dict:
    return {"status": "paused"}


@app.post("/v1/workflow-engine/instances/{instance_id}/terminate")
async def terminate(instance_id: str) -> dict:
    return {"status": "terminated"}


@app.post("/v1/tool-orchestration/circuit-breaker/force-open")
async def force_open(body: dict) -> dict:
    return {"status": "opened"}


@app.post("/v1/human-oversight/requests")
async def create_request(body: dict) -> dict:
    return {"id": "stub-request-id"}


@app.post("/v1/auditability/events")
async def auditability_events(body: dict) -> dict:
    return {"status": "ok"}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

@app.get("/v1/multi-tenancy/tenants/{tenant_id}/gate")
async def gate(tenant_id: str, module: str | None = None) -> dict:
    return {"allowed": True, "reason": "active"}
