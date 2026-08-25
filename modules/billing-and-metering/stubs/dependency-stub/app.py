"""Dependency-stub service for Billing and Metering.

Stands in for this module's two real platform-peer dependencies --
FinOps (Module 26) and Auditability (Module 20) -- so the Metering
Service's full metering-and-invoice path is exercised end to end
without either real peer deployed alongside it, per the LLD's
Deployability and Testability Contract.
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Billing and Metering dependency stub")


@app.get("/v1/finops/cost-reports/{tenant_id}")
async def cost_report(tenant_id: str, period: str) -> dict:
    return {
        "tenant_id": tenant_id, "period": period, "llm_gateway_spend": 0.0, "other_usage_cost": 0.0,
        "total_cost": 0.0, "forecast_amount": None, "budget_policy": None,
        "utilisation_ratio": None, "alert": False,
    }


@app.get("/v1/auditability/events")
async def list_events() -> dict:
    return {"items": [], "total": 0, "limit": 1, "offset": 0}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
