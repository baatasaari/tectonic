"""In-memory fakes for the ports in core/ports.py — the unit-test tier,
mirroring the other modules' core/fakes.py.
"""
from __future__ import annotations

import copy
from typing import Any

from graph_db.core.domain import EdgeRecord, NodeRecord


class InMemoryGraphRepository:
    def __init__(self) -> None:
        self.nodes: dict[str, NodeRecord] = {}
        self.edges: dict[str, EdgeRecord] = {}

    async def create_node(self, record: NodeRecord) -> NodeRecord:
        self.nodes[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_node(self, tenant_id: str, node_id: str) -> NodeRecord | None:
        rec = self.nodes.get(node_id)
        if rec is None or rec.tenant_id != tenant_id:
            return None
        return copy.deepcopy(rec)

    async def create_edge(self, record: EdgeRecord) -> EdgeRecord:
        self.edges[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def list_outgoing_edges(self, tenant_id: str, node_id: str) -> list[EdgeRecord]:
        return [
            copy.deepcopy(e) for e in self.edges.values()
            if e.tenant_id == tenant_id and e.from_node_id == node_id
        ]

    async def list_incoming_edges(self, tenant_id: str, node_id: str) -> list[EdgeRecord]:
        return [
            copy.deepcopy(e) for e in self.edges.values()
            if e.tenant_id == tenant_id and e.to_node_id == node_id
        ]

    async def count_nodes(self, tenant_id: str) -> int:
        return sum(1 for n in self.nodes.values() if n.tenant_id == tenant_id)

    async def count_edges_by_kind(self, tenant_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.edges.values():
            if e.tenant_id == tenant_id:
                counts[e.edge_kind.value] = counts.get(e.edge_kind.value, 0) + 1
        return counts


class InMemoryAuditabilityClient:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(self, event: dict[str, Any]) -> None:
        self.events.append(copy.deepcopy(event))
