"""Dependency-stub service for Multi-tenancy.

Stands in for a real platform module's tenant-scoped list endpoint (the
default configured probe target, Agent Cards' own `GET
/v1/agent-cards`), so the Isolation Probe Service's full clean/breach
path is exercised end to end without any real platform peer deployed
alongside it, per the LLD's Deployability and Testability Contract.

Deliberately includes one item belonging to a *different* tenant no
matter which `tenant_id` is queried -- this stub is the breach-detection
fixture, proving the probe actually looks at each item's own tenant_id
rather than trusting the query parameter blindly.
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Multi-tenancy dependency stub")


@app.get("/v1/agent-cards")
async def list_agent_cards(tenant_id: str, limit: int = 200, offset: int = 0) -> dict:
    items = [
        {"id": "card-1", "tenant_id": tenant_id, "name": "own record"},
        {"id": "card-2", "tenant_id": "a-different-tenant", "name": "leaked record"},
    ]
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
