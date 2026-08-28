"""Dependency-stub service for Vector DB.

Stands in for LLM Gateway's embeddings endpoint (LLD's Deployability and
Testability Contract: "Runs and tests fully with LLM Gateway stubbed
(canned embeddings)"). Real Qdrant runs in-process via the embedded
client — no stub needed for it.
"""
from __future__ import annotations

import hashlib

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Vector DB dependency stub")

_DIMENSION = 8


class EmbeddingsRequest(BaseModel):
    input: str
    model: str = "text-embedding-3-small"


@app.post("/v1/embeddings")
async def embeddings(body: EmbeddingsRequest) -> dict:
    digest = hashlib.sha256(f"{body.model}:{body.input}".encode()).digest()
    vector = [(digest[i % len(digest)] / 255.0) * 2 - 1 for i in range(_DIMENSION)]
    return {"data": [{"embedding": vector, "index": 0}], "model": body.model}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

@app.get("/v1/multi-tenancy/tenants/{tenant_id}/gate")
async def gate(tenant_id: str, module: str | None = None) -> dict:
    return {"allowed": True, "reason": "active"}
