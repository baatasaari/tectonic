"""Abstract ports the ingestion pipeline depends on: persistence, blob
storage, and the Vector DB / Graph DB downstream dependencies."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from knowledge_base.core.domain import (
    ChunkRecord,
    DocumentRecord,
    DocumentVersionRecord,
    PolicyTagRecord,
)


@dataclass
class ParsedContent:
    text: str
    headings: list[tuple[int, str]] = field(default_factory=list)  # (char_offset, heading_text)


class KnowledgeBaseRepository(Protocol):
    async def create_document(self, record: DocumentRecord) -> DocumentRecord: ...

    async def get_document(self, document_id: str) -> DocumentRecord | None: ...

    async def update_document(self, record: DocumentRecord) -> DocumentRecord: ...

    async def list_stale_candidates(self, tenant_id: str) -> list[DocumentRecord]: ...

    async def list_documents(self, tenant_id: str) -> list[DocumentRecord]: ...

    async def create_version(self, record: DocumentVersionRecord) -> DocumentVersionRecord: ...

    async def get_version(self, version_id: str) -> DocumentVersionRecord | None: ...

    async def list_versions(self, document_id: str) -> list[DocumentVersionRecord]: ...

    async def find_version_by_content_hash(
        self, document_id: str, content_hash: str
    ) -> DocumentVersionRecord | None: ...

    async def create_chunks(self, records: list[ChunkRecord]) -> list[ChunkRecord]: ...

    async def list_chunks_by_version(self, document_version_id: str) -> list[ChunkRecord]: ...

    async def list_chunks_by_policy_tag(self, tenant_id: str, policy_tag: str) -> list[ChunkRecord]: ...

    async def create_policy_tag(self, record: PolicyTagRecord) -> PolicyTagRecord: ...

    async def list_policy_tags(self, tenant_id: str) -> list[PolicyTagRecord]: ...


class BlobStorage(Protocol):
    async def put(self, content: bytes) -> str:
        """Stores raw bytes, returns an opaque blob_ref."""
        ...

    async def get(self, blob_ref: str) -> bytes: ...


class VectorDBClient(Protocol):
    async def embed_and_store(self, chunks: list[dict[str, Any]]) -> None: ...


class GraphDBClient(Protocol):
    async def extract_entities(self, chunks: list[dict[str, Any]]) -> None: ...
