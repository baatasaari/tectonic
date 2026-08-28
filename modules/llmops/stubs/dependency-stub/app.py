"""Dependency-stub service for LLMOps.

Stands in for this module's one real platform-peer dependency --
Evaluation Framework (Module 18) -- so the Canary Evaluation Service's
gate path is exercised end to end without Evaluation Framework itself
deployed alongside it, per the LLD's Deployability and Testability
Contract.
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="LLMOps dependency stub")


@app.get("/v1/evaluation-framework/scores")
async def list_scores(tenant_id: str, agent_ref: str, limit: int = 200, offset: int = 0) -> dict:
    # Canned, passing score history -- a real Evaluation Framework would return this
    # version's actual metric-score records; this stub just proves the wiring, matching
    # this platform's "stub returns canned data, real behavior is exercised by the unit
    # tier's stub clients with controllable scores" convention.
    items = [
        {
            "id": f"score-{i}", "metric_name": "faithfulness", "score": 0.95, "threshold": 0.8, "passed": True,
            "created_at": "2026-01-01T00:00:00Z",
        }
        for i in range(10)
    ]
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

@app.get("/v1/multi-tenancy/tenants/{tenant_id}/gate")
async def gate(tenant_id: str, module: str | None = None) -> dict:
    return {"allowed": True, "reason": "active"}
