"""Request/response models for `/v1/graph-db/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class CreateNodeRequest(BaseModel):
    entity_type: str
    name: str
    attributes: dict[str, Any] = {}


class NodeSchema(BaseModel):
    id: str
    entity_type: str
    name: str
    attributes: dict[str, Any]
    created_at: datetime


class CreateEdgeRequest(BaseModel):
    from_node_id: str
    to_node_id: str
    relationship_type: str
    edge_kind: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    confidence: float | None = None
    source_ref: str = ""


class EdgeSchema(BaseModel):
    id: str
    from_node_id: str
    to_node_id: str
    relationship_type: str
    edge_kind: str
    valid_from: datetime
    valid_to: datetime | None
    confidence: float | None
    source_ref: str
    created_at: datetime


class QueryRequest(BaseModel):
    query_type: Literal["neighbours", "path"]
    node_id: str
    target_node_id: str | None = None
    depth: int | None = None
    edge_kind: str | None = None
    as_of: datetime | None = None


class QueryResponse(BaseModel):
    nodes: list[NodeSchema]
    edges: list[EdgeSchema]
    path: list[str] | None = None
