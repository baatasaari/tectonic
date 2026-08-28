"""Dependency-stub service for Knowledge Base.

Stands in for both downstream module dependencies named in the LLD's
Deployability and Testability Contract: Vector DB (embed_and_store) and
Graph DB (extract_entities) — this module can be tested purely on
ingestion, chunking, versioning and policy-tagging correctness without a
real embedding or graph backend.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Knowledge Base dependency stub")


class ChunksRequest(BaseModel):
    chunks: list[dict[str, Any]] = []


@app.post("/v1/embed-and-store")
async def embed_and_store(body: ChunksRequest) -> dict:
    return {"status": "ok", "count": len(body.chunks)}


@app.post("/v1/extract-entities")
async def extract_entities(body: ChunksRequest) -> dict:
    return {"status": "ok", "count": len(body.chunks)}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

@app.get("/v1/multi-tenancy/tenants/{tenant_id}/gate")
async def gate(tenant_id: str, module: str | None = None) -> dict:
    return {"allowed": True, "reason": "active"}
