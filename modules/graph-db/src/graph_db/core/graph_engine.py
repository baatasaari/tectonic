"""Write Coordinator + Query Engine (LLD §2 sub-components) — the module's
orchestrator. Traversal ("neighbours") and shortest-path queries are
breadth-first over both edge directions, respecting the Temporal Filter
and an optional `edge_kind` filter at every hop, bounded by
`query.default_max_traversal_depth`.
"""
from __future__ import annotations

from datetime import datetime

from graph_db.core import temporal
from graph_db.core.causal_validator import validate_edge_kind
from graph_db.core.domain import EdgeRecord, NodeRecord, Subgraph, new_id, now
from graph_db.core.ports import AuditabilityClient, GraphRepository


class GraphEngine:
    def __init__(self, repository: GraphRepository, auditability: AuditabilityClient, max_depth: int) -> None:
        self._repository = repository
        self._auditability = auditability
        self._max_depth = max_depth

    async def write_node(self, *, tenant_id: str, entity_type: str, name: str, attributes: dict) -> NodeRecord:
        record = NodeRecord(id=new_id(), tenant_id=tenant_id, entity_type=entity_type, name=name, attributes=attributes)
        record = await self._repository.create_node(record)
        await self._emit_audit({"event": "node_created", "tenant_id": tenant_id, "node_id": record.id, "entity_type": entity_type})
        return record

    async def write_edge(
        self, *, tenant_id: str, from_node_id: str, to_node_id: str, relationship_type: str, edge_kind: str | None,
        valid_from: datetime | None = None, valid_to: datetime | None = None, confidence: float | None = None,
        source_ref: str = "",
    ) -> EdgeRecord:
        kind = validate_edge_kind(edge_kind)
        record = EdgeRecord(
            id=new_id(), tenant_id=tenant_id, from_node_id=from_node_id, to_node_id=to_node_id,
            relationship_type=relationship_type, edge_kind=kind, valid_from=valid_from or now(),
            valid_to=valid_to, confidence=confidence, source_ref=source_ref,
        )
        record = await self._repository.create_edge(record)
        await self._emit_audit({
            "event": "edge_created", "tenant_id": tenant_id, "edge_id": record.id, "edge_kind": kind.value,
            "source_ref": source_ref,
        })
        return record

    async def neighbours(
        self, tenant_id: str, node_id: str, *, depth: int, edge_kind_filter: str | None = None,
        as_of: datetime | None = None,
    ) -> Subgraph:
        as_of = as_of or now()
        depth = max(0, min(depth, self._max_depth))

        visited_nodes = {node_id}
        visited_edges: dict[str, EdgeRecord] = {}
        frontier = [node_id]

        for _ in range(depth):
            next_frontier: list[str] = []
            for nid in frontier:
                for edge in await self._adjacent_edges(tenant_id, nid):
                    if edge_kind_filter and edge.edge_kind.value != edge_kind_filter:
                        continue
                    if not temporal.is_valid_at(edge, as_of):
                        continue
                    visited_edges[edge.id] = edge
                    other = edge.to_node_id if edge.from_node_id == nid else edge.from_node_id
                    if other not in visited_nodes:
                        visited_nodes.add(other)
                        next_frontier.append(other)
            frontier = next_frontier
            if not frontier:
                break

        nodes = [n for n in [await self._repository.get_node(tenant_id, nid) for nid in visited_nodes] if n]
        return Subgraph(nodes=nodes, edges=list(visited_edges.values()))

    async def path(
        self, tenant_id: str, node_id: str, target_node_id: str, *, depth: int, edge_kind_filter: str | None = None,
        as_of: datetime | None = None,
    ) -> Subgraph:
        as_of = as_of or now()
        depth = max(0, min(depth, self._max_depth))

        if node_id == target_node_id:
            node = await self._repository.get_node(tenant_id, node_id)
            found_nodes = [node] if node else []
            return Subgraph(nodes=found_nodes, edges=[], node_path=[node_id] if node else [])

        visited = {node_id}
        predecessor_edge: dict[str, EdgeRecord] = {}
        predecessor_node: dict[str, str] = {}
        frontier = [node_id]
        found = False

        for _ in range(depth):
            next_frontier: list[str] = []
            for nid in frontier:
                for edge in await self._adjacent_edges(tenant_id, nid):
                    if edge_kind_filter and edge.edge_kind.value != edge_kind_filter:
                        continue
                    if not temporal.is_valid_at(edge, as_of):
                        continue
                    other = edge.to_node_id if edge.from_node_id == nid else edge.from_node_id
                    if other in visited:
                        continue
                    visited.add(other)
                    predecessor_edge[other] = edge
                    predecessor_node[other] = nid
                    if other == target_node_id:
                        found = True
                        break
                    next_frontier.append(other)
                if found:
                    break
            if found:
                break
            frontier = next_frontier
            if not frontier:
                break

        if not found:
            return Subgraph(nodes=[], edges=[], node_path=[])

        path_ids = [target_node_id]
        edges_in_path: list[EdgeRecord] = []
        cur = target_node_id
        while cur != node_id:
            edges_in_path.append(predecessor_edge[cur])
            cur = predecessor_node[cur]
            path_ids.append(cur)
        path_ids.reverse()
        edges_in_path.reverse()

        nodes = [n for n in [await self._repository.get_node(tenant_id, nid) for nid in path_ids] if n]
        return Subgraph(nodes=nodes, edges=edges_in_path, node_path=path_ids)

    async def _adjacent_edges(self, tenant_id: str, node_id: str) -> list[EdgeRecord]:
        out_edges = await self._repository.list_outgoing_edges(tenant_id, node_id)
        in_edges = await self._repository.list_incoming_edges(tenant_id, node_id)
        return out_edges + in_edges

    async def _emit_audit(self, event: dict) -> None:
        # Fire-and-forget, matching the other modules' AuditabilityClient
        # usage: a logging side-channel, not a transactional dependency
        # of the write itself.
        await self._auditability.emit(event)
