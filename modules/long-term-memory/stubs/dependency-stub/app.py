"""Dependency-stub service for Long-Term Memory.

Stands in for every external module dependency named in the LLD's
Deployability and Testability Contract: Vector DB, Graph DB, LLM Gateway
and Evaluation Framework/Guardrails — "this module owns fact/episode
data directly in Postgres but delegates semantic and procedural storage
to other modules, so its own tests focus on consolidation, forgetting
and cross-agent visibility logic against stubbed storage backends."
"""
from __future__ import annotations

import uuid

from fastapi import FastAPI

app = FastAPI(title="Long-Term Memory dependency stub")

_points: dict[str, str] = {}
_nodes: dict[str, str] = {}


@app.post("/v1/vector-db/points")
async def index_point(body: dict) -> dict:
    point_id = str(uuid.uuid4())
    _points[point_id] = body.get("content", "")
    return {"id": point_id}


@app.post("/v1/vector-db/query")
async def query_points(body: dict) -> dict:
    text = (body.get("text") or "").lower()
    results = [
        {"id": pid, "score": 1.0 if text in content.lower() else 0.1, "payload": {"content": content}}
        for pid, content in _points.items()
    ]
    results.sort(key=lambda r: r["score"], reverse=True)
    return {"results": results[: body.get("top_k", 10)]}


@app.delete("/v1/vector-db/points/{point_id}")
async def delete_point(point_id: str) -> dict:
    _points.pop(point_id, None)
    return {"status": "deleted"}


@app.post("/v1/graph-db/nodes")
async def create_node(body: dict) -> dict:
    node_id = str(uuid.uuid4())
    _nodes[node_id] = body.get("name", "")
    return {"id": node_id, "entity_type": body.get("entity_type", ""), "name": body.get("name", ""), "attributes": body.get("attributes", {}), "created_at": "2026-01-01T00:00:00Z"}


@app.post("/v1/graph-db/query")
async def query_graph(body: dict) -> dict:
    return {"nodes": [], "edges": [], "path": None}


@app.post("/v1/reflect")
async def reflect(body: dict) -> dict:
    context = body.get("context", "")
    return {"reflection": f"On reflection: {context[:80]}"}


@app.post("/v1/guardrails/check-visibility")
async def check_visibility(body: dict) -> dict:
    return {"allowed": True}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
