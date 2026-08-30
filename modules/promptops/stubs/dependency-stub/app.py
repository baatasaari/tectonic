"""Dependency-stub service for PromptOps.

Stands in for this module's two real platform-peer dependencies --
Evaluation Framework (Module 18) and LLM Gateway (Module 3) -- so the
A/B testing, drift detection and reflection paths are all exercised
end to end without either real peer deployed alongside it, per the
LLD's Deployability and Testability Contract.
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="PromptOps dependency stub")


@app.get("/v1/evaluation-framework/scores")
async def list_scores(tenant_id: str, agent_ref: str, limit: int = 200, offset: int = 0) -> dict:
    # Canned, passing score history -- a real Evaluation Framework would return this
    # prompt version's actual metric-score records; this stub just proves the wiring,
    # matching this platform's "stub returns canned data, real behavior is exercised by
    # the unit tier's stub clients with controllable scores" convention.
    items = [
        {
            "id": f"score-{i}", "metric_name": "groundedness", "score": 0.95, "threshold": 0.8, "passed": True,
            "created_at": "2026-01-01T00:00:00Z",
        }
        for i in range(15)
    ]
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@app.post("/v1/llm-gateway/chat/completions")
async def chat_completions() -> dict:
    return {
        "id": "cmpl-stub", "object": "chat.completion", "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "A reflected, improved template."}, "finish_reason": "stop"}],
        "provider_used": "stub", "cache_hit": False, "cost": 0.0, "usage": {"prompt_tokens": 0, "completion_tokens": 0},
    }


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

@app.get("/v1/multi-tenancy/tenants/{tenant_id}/gate")
async def gate(tenant_id: str, module: str | None = None) -> dict:
    return {"allowed": True, "reason": "active"}
