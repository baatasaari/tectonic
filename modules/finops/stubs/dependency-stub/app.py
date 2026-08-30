"""Dependency-stub service for FinOps.

Stands in for this module's one real platform-peer dependency -- LLM
Gateway (Module 3) -- so the Usage Aggregation Service's live-spend path
is exercised end to end without LLM Gateway itself deployed alongside
it, per the LLD's Deployability and Testability Contract. Plays exactly
the two real endpoints `HTTPLLMGatewayClient` calls:
`GET /v1/llm-gateway/admin/virtual-keys` and
`GET /v1/llm-gateway/admin/budgets/{id}`.
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="FinOps dependency stub")

# Canned data -- a real LLM Gateway would return this tenant's actual virtual
# keys and their live current_spend; this stub just proves the wiring,
# matching this platform's "stub returns canned data, real behavior is
# exercised by the unit tier's stub clients with controllable spend"
# convention.
_VIRTUAL_KEYS = [
    {"id": "vk-demo-1", "tenant_id": "default", "budget_policy_ref": "bp-demo"},
]
_BUDGETS = {
    "bp-demo": {"id": "bp-demo", "period": "monthly", "limit_amount": 1000.0, "current_spend": 42.5, "alert_threshold_pct": 0.8},
}


@app.get("/v1/llm-gateway/admin/virtual-keys")
async def list_virtual_keys(tenant_id: str, limit: int = 200, offset: int = 0) -> dict:
    items = [vk for vk in _VIRTUAL_KEYS if vk["tenant_id"] == tenant_id]
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@app.get("/v1/llm-gateway/admin/budgets/{budget_policy_id}")
async def get_budget(budget_policy_id: str) -> dict:
    return _BUDGETS.get(budget_policy_id, {"id": budget_policy_id, "current_spend": 0.0})


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

@app.get("/v1/multi-tenancy/tenants/{tenant_id}/gate")
async def gate(tenant_id: str, module: str | None = None) -> dict:
    return {"allowed": True, "reason": "active"}
