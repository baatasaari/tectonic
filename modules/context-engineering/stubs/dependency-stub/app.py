"""Dependency-stub service for Context Engineering.

Stands in for LLM Gateway (summarisation) and the Evaluation Framework
feedback feed (LLD's Deployability and Testability Contract: "Runs and
tests fully with Evaluation Framework's feedback feed stubbed with canned
prioritisation signals").
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Context Engineering dependency stub")


class SummariseRequest(BaseModel):
    content: str
    target_tokens: int
    tenant_id: str


@app.post("/v1/summarise")
async def summarise(body: SummariseRequest) -> dict:
    words = body.content.split()
    keep = max(1, min(len(words), body.target_tokens))
    return {"summary": " ".join(words[:keep])}


@app.get("/v1/evaluation/feature-feedback")
async def feature_feedback(tenant_id: str, task_type: str) -> dict:
    return {"feedback": {}}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

@app.get("/v1/multi-tenancy/tenants/{tenant_id}/gate")
async def gate(tenant_id: str, module: str | None = None) -> dict:
    return {"allowed": True, "reason": "active"}
