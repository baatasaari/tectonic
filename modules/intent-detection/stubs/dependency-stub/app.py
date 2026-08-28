"""Dependency-stub service for Intent Detection.

Stands in for the LLM Gateway fallback path (LLD's Deployability and
Testability Contract: "Runs and tests fully with LLM Gateway stubbed for
the compositional fallback path").
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Intent Detection dependency stub")


class ClassifyStructuredRequest(BaseModel):
    text: str
    taxonomy: list[dict]
    tenant_id: str


@app.post("/v1/classify-structured")
async def classify_structured(body: ClassifyStructuredRequest) -> dict:
    intents = [{"name": t["name"], "confidence": 0.9 - 0.1 * i} for i, t in enumerate(body.taxonomy[:2])]
    return {"intents": intents}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

@app.get("/v1/multi-tenancy/tenants/{tenant_id}/gate")
async def gate(tenant_id: str, module: str | None = None) -> dict:
    return {"allowed": True, "reason": "active"}
