"""Abstract ports the Graph Engine depends on: persistence and the
Auditability dependency (best-effort event publishing, per the LLD's
Write Coordinator -> Auditability edge)."""
from __future__ import annotations

from typing import Any, Protocol

from graph_db.core.domain import EdgeRecord, NodeRecord


class GraphRepository(Protocol):
    async def create_node(self, record: NodeRecord) -> NodeRecord: ...

    async def get_node(self, tenant_id: str, node_id: str) -> NodeRecord | None: ...

    async def create_edge(self, record: EdgeRecord) -> EdgeRecord: ...

    async def list_outgoing_edges(self, tenant_id: str, node_id: str) -> list[EdgeRecord]: ...

    async def list_incoming_edges(self, tenant_id: str, node_id: str) -> list[EdgeRecord]: ...

    async def count_nodes(self, tenant_id: str) -> int: ...

    async def count_edges_by_kind(self, tenant_id: str) -> dict[str, int]: ...


class AuditabilityClient(Protocol):
    async def emit(self, event: dict[str, Any]) -> None: ...
