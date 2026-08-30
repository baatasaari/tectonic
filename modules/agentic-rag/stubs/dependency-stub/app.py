"""Dependency-stub service for Agentic RAG.

Stands in for Vector DB, Graph DB, Knowledge Base and LLM Gateway (LLD's
Deployability and Testability Contract: "Runs and tests fully with Vector
DB, Graph DB, Knowledge Base, and LLM Gateway stubbed, using canned
retrieval results and groundedness scores").
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Agentic RAG dependency stub")


class SearchRequest(BaseModel):
    query: str
    scope: list[str]
    tenant_id: str


@app.post("/v1/vector-db/search")
async def vector_search(body: SearchRequest) -> dict:
    return {"results": [{"content": f"stub vector passage about: {body.query}", "provenance": {"source_document": "vector-doc-1"}, "score": 0.8}]}


@app.post("/v1/graph-db/search")
async def graph_search(body: SearchRequest) -> dict:
    return {"results": [{"content": f"stub graph relationship about: {body.query}", "provenance": {"source_document": "graph-doc-1"}, "score": 0.7}]}


@app.post("/v1/knowledge-base/lookup")
async def kb_lookup(body: SearchRequest) -> dict:
    return {"results": [{"content": f"stub structured fact about: {body.query}", "provenance": {"source_document": "kb-doc-1"}, "score": 0.9}]}


class GroundednessRequest(BaseModel):
    query: str
    items: list[str]
    tenant_id: str


@app.post("/v1/rag/assess-groundedness")
async def assess_groundedness(body: GroundednessRequest) -> dict:
    return {"score": 0.9, "gaps": ""}


class ReformulateRequest(BaseModel):
    query: str
    gaps: str
    tenant_id: str


@app.post("/v1/rag/reformulate")
async def reformulate(body: ReformulateRequest) -> dict:
    return {"revised_query": f"{body.query} (revised)"}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

@app.get("/v1/multi-tenancy/tenants/{tenant_id}/gate")
async def gate(tenant_id: str, module: str | None = None) -> dict:
    return {"allowed": True, "reason": "active"}
