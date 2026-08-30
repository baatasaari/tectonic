"""Dependency-stub service for Agent Cards.

Stands in for this module's platform-peer dependencies -- Evaluation
Framework (Module 18) and Regulatory Compliance (Module 17), so the
Trust Score Calculator's full weighted-combination path is exercised
end to end, and Multi-tenancy (Module 30), so EntitlementGateMiddleware
has something to call -- without any real peer deployed alongside it,
per the LLD's Deployability and Testability Contract.
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Agent Cards dependency stub")


@app.get("/v1/evaluation-framework/scores")
async def list_scores(tenant_id: str, agent_ref: str, limit: int = 200, offset: int = 0) -> dict:
    # Canned score history -- a real Evaluation Framework would return this agent's
    # actual metric-score records; this stub just proves the wiring, matching this
    # platform's "stub returns canned data, real behavior is exercised by the unit
    # tier's stub clients with controllable scores" convention.
    return {
        "items": [
            {
                "id": "score-1", "metric_name": "faithfulness", "score": 0.85, "threshold": 0.8, "passed": True,
                "created_at": "2026-01-01T00:00:00Z",
            }
        ],
        "total": 1, "limit": limit, "offset": offset,
    }


@app.get("/v1/regulatory-compliance/coverage")
async def coverage(tenant_id: str, framework_name: str) -> dict:
    return {"tenant_id": tenant_id, "framework_name": framework_name, "coverage_percentage": 90.0, "gaps": []}


@app.get("/v1/multi-tenancy/tenants/{tenant_id}/gate")
async def gate(tenant_id: str, module: str | None = None) -> dict:
    # An always-allow stub: real entitlement denial is exercised by the unit tier's
    # own EntitlementGateMiddleware tests with a controllable Multi-tenancy stub.
    return {"allowed": True, "reason": "active"}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
