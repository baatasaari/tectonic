"""Framework-agnostic domain objects (LLD §3 "Data model (graph schema,
not relational)")."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class EdgeKind(StrEnum):
    CAUSAL = "causal"
    CORRELATIONAL = "correlational"
    STRUCTURAL = "structural"


class MissingEdgeKindError(Exception):
    def __init__(self) -> None:
        super().__init__("edge_kind is required: must be one of causal, correlational, structural")


class InvalidEdgeKindError(Exception):
    def __init__(self, value: str) -> None:
        super().__init__(f"invalid edge_kind: {value!r} — must be one of causal, correlational, structural")


class NodeNotFoundError(Exception):
    def __init__(self, node_id: str) -> None:
        super().__init__(f"node not found: {node_id}")


@dataclass
class NodeRecord:
    id: str
    tenant_id: str
    entity_type: str
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=now)


@dataclass
class EdgeRecord:
    id: str
    tenant_id: str
    from_node_id: str
    to_node_id: str
    relationship_type: str
    edge_kind: EdgeKind
    valid_from: datetime = field(default_factory=now)
    valid_to: datetime | None = None
    confidence: float | None = None
    source_ref: str = ""
    created_at: datetime = field(default_factory=now)


@dataclass
class Subgraph:
    nodes: list[NodeRecord] = field(default_factory=list)
    edges: list[EdgeRecord] = field(default_factory=list)
    node_path: list[str] | None = None  # ordered node ids, set only for "path" queries
