"""In-memory fakes for the ports in core/ports.py — the unit-test tier,
mirroring the other modules' core/fakes.py.
"""
from __future__ import annotations

import copy
import hashlib
from typing import Any

from knowledge_base.core.domain import (
    ChunkRecord,
    DocumentRecord,
    DocumentVersionRecord,
    PolicyTagRecord,
)


class InMemoryKnowledgeBaseRepository:
    def __init__(self) -> None:
        self.documents: dict[str, DocumentRecord] = {}
        self.versions: dict[str, DocumentVersionRecord] = {}
        self.chunks: dict[str, ChunkRecord] = {}
        self.policy_tags: dict[str, PolicyTagRecord] = {}

    async def create_document(self, record: DocumentRecord) -> DocumentRecord:
        self.documents[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_document(self, document_id: str) -> DocumentRecord | None:
        rec = self.documents.get(document_id)
        return copy.deepcopy(rec) if rec else None

    async def update_document(self, record: DocumentRecord) -> DocumentRecord:
        self.documents[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def list_stale_candidates(self, tenant_id: str) -> list[DocumentRecord]:
        return [copy.deepcopy(d) for d in self.documents.values() if d.tenant_id == tenant_id]

    async def list_documents(self, tenant_id: str) -> list[DocumentRecord]:
        return [copy.deepcopy(d) for d in self.documents.values() if d.tenant_id == tenant_id]

    async def create_version(self, record: DocumentVersionRecord) -> DocumentVersionRecord:
        self.versions[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_version(self, version_id: str) -> DocumentVersionRecord | None:
        rec = self.versions.get(version_id)
        return copy.deepcopy(rec) if rec else None

    async def list_versions(self, document_id: str) -> list[DocumentVersionRecord]:
        return [copy.deepcopy(v) for v in self.versions.values() if v.document_id == document_id]

    async def find_version_by_content_hash(
        self, document_id: str, content_hash: str
    ) -> DocumentVersionRecord | None:
        for v in self.versions.values():
            if v.document_id == document_id and v.content_hash == content_hash:
                return copy.deepcopy(v)
        return None

    async def create_chunks(self, records: list[ChunkRecord]) -> list[ChunkRecord]:
        for record in records:
            self.chunks[record.id] = copy.deepcopy(record)
        return [copy.deepcopy(r) for r in records]

    async def list_chunks_by_version(
        self, document_version_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[ChunkRecord], int]:
        matching = sorted(
            (c for c in self.chunks.values() if c.document_version_id == document_version_id),
            key=lambda c: c.chunk_index,
        )
        sliced = [copy.deepcopy(c) for c in matching[offset : offset + limit]]
        return sliced, len(matching)

    async def list_chunks_by_policy_tag(
        self, tenant_id: str, policy_tag: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[ChunkRecord], int]:
        version_ids_for_tenant = {
            v.id for v in self.versions.values()
            if self.documents.get(v.document_id) and self.documents[v.document_id].tenant_id == tenant_id
        }
        matching = sorted(
            (
                c for c in self.chunks.values()
                if c.document_version_id in version_ids_for_tenant and policy_tag in c.policy_tags
            ),
            key=lambda c: (c.document_version_id, c.chunk_index),
        )
        sliced = [copy.deepcopy(c) for c in matching[offset : offset + limit]]
        return sliced, len(matching)

    async def create_policy_tag(self, record: PolicyTagRecord) -> PolicyTagRecord:
        self.policy_tags[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def list_policy_tags(self, tenant_id: str) -> list[PolicyTagRecord]:
        return [copy.deepcopy(t) for t in self.policy_tags.values() if t.tenant_id == tenant_id]


class InMemoryBlobStorage:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    async def put(self, content: bytes) -> str:
        ref = hashlib.sha256(content).hexdigest()
        self.blobs[ref] = content
        return ref

    async def get(self, blob_ref: str) -> bytes:
        return self.blobs[blob_ref]


class StubVectorDBClient:
    def __init__(self) -> None:
        self.stored: list[dict[str, Any]] = []

    async def embed_and_store(self, chunks: list[dict[str, Any]]) -> None:
        self.stored.extend(chunks)


class StubGraphDBClient:
    def __init__(self) -> None:
        self.extracted: list[dict[str, Any]] = []

    async def extract_entities(self, chunks: list[dict[str, Any]]) -> None:
        self.extracted.extend(chunks)
