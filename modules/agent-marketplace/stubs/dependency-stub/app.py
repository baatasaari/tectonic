"""Dependency-stub service for Agent Marketplace.

Stands in for this module's one real platform-peer dependency -- Agent
Cards (Module 23) -- so the Catalogue Sync Service's snapshot path is
exercised end to end without Agent Cards itself deployed alongside it,
per the LLD's Deployability and Testability Contract.
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Agent Marketplace dependency stub")

_CARD = {
    "id": "card-1", "tenant_id": "acme", "agent_ref": "search-agent", "name": "Search Agent",
    "description": "Finds things", "url": "http://search-agent.example",
    "skills": [{"id": "search", "name": "Search", "description": "Web search"}],
    "trust_score": 0.85,
}


@app.get("/v1/agent-cards/{card_id}")
async def get_card(card_id: str) -> dict:
    # Canned card -- a real Agent Cards would return the actual registered card; this stub
    # just proves the wiring, matching this platform's "stub returns canned data, real
    # behavior is exercised by the unit tier's stub clients with controllable cards"
    # convention.
    return _CARD


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
