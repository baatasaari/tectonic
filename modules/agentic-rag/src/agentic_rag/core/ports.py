"""Abstract ports the retrieval loop depends on: persistence, the three
data-layer retrieval backends, and LLM Gateway for groundedness/reformulation.
"""
from __future__ import annotations

from typing import Protocol

from agentic_rag.core.domain import (
    GroundednessAssessment,
    RetrievalHopRecord,
    RetrievalRequestRecord,
    RetrievalResultRecord,
    RetrievedItem,
)


class RAGRepository(Protocol):
    async def create_request(self, record: RetrievalRequestRecord) -> RetrievalRequestRecord: ...

    async def get_request(self, request_id: str) -> RetrievalRequestRecord | None: ...

    async def create_hop(self, record: RetrievalHopRecord) -> RetrievalHopRecord: ...

    async def list_hops(self, request_id: str) -> list[RetrievalHopRecord]: ...

    async def create_result(self, record: RetrievalResultRecord) -> RetrievalResultRecord: ...

    async def get_result(self, request_id: str) -> RetrievalResultRecord | None: ...


class VectorDBClient(Protocol):
    async def search(self, *, query: str, scope: list[str], tenant_id: str) -> list[RetrievedItem]: ...


class GraphDBClient(Protocol):
    async def search(self, *, query: str, scope: list[str], tenant_id: str) -> list[RetrievedItem]: ...


class KnowledgeBaseClient(Protocol):
    async def symbolic_lookup(self, *, query: str, scope: list[str], tenant_id: str) -> list[RetrievedItem]: ...


class LLMGatewayClient(Protocol):
    async def assess_groundedness(
        self, *, query: str, items: list[RetrievedItem], tenant_id: str
    ) -> GroundednessAssessment: ...

    async def reformulate(self, *, query: str, gaps: str, tenant_id: str) -> str: ...
