"""Dependency-stub service for Deployment Strategy.

Stands in for this module's two real platform-peer dependencies --
Evaluation Framework (Module 18) and FinOps (Module 26) -- so the
Canary Health Calculator's full gate path is exercised end to end
without either real peer deployed alongside it, per the LLD's
Deployability and Testability Contract.
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Deployment Strategy dependency stub")


@app.get("/v1/evaluation-framework/scores")
async def list_scores(tenant_id: str, agent_ref: str, limit: int = 200, offset: int = 0) -> dict:
    # Canned, passing score history -- a real Evaluation Framework would return this
    # deployment's actual groundedness score records; this stub just proves the wiring,
    # matching this platform's "stub returns canned data, real behavior is exercised by
    # the unit tier's stub clients with controllable scores" convention.
    items = [
        {
            "id": f"score-{i}", "metric_name": "groundedness", "score": 0.95, "threshold": 0.8, "passed": True,
            "created_at": "2026-01-01T00:00:00Z",
        }
        for i in range(10)
    ]
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@app.get("/v1/finops/cost-reports/{tenant_id}")
async def cost_report(tenant_id: str, period: str, budget_policy_id: str | None = None) -> dict:
    return {
        "tenant_id": tenant_id, "period": period, "llm_gateway_spend": 10.0, "other_usage_cost": 0.0,
        "total_cost": 10.0, "forecast_amount": None, "budget_policy": None,
        "utilisation_ratio": 0.2 if budget_policy_id else None, "alert": False,
    }


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
