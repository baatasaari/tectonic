"""SQLAlchemy-backed implementation of KnowledgeBaseRepository (LLD §3)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_base.core.domain import (
    ChunkRecord,
    DocumentRecord,
    DocumentStatus,
    DocumentVersionRecord,
    PolicyTagRecord,
    SourceType,
)
from knowledge_base.db import models


def _document_to_domain(m: models.Document) -> DocumentRecord:
    return DocumentRecord(
        id=str(m.id), tenant_id=m.tenant_id, title=m.title, source_type=SourceType(m.source_type),
        current_version_id=str(m.current_version_id) if m.current_version_id else None,
        status=DocumentStatus(m.status), staleness_threshold_days=m.staleness_threshold_days,
        last_reviewed_at=m.last_reviewed_at, created_at=m.created_at,
    )


def _version_to_domain(m: models.DocumentVersion) -> DocumentVersionRecord:
    return DocumentVersionRecord(
        id=str(m.id), document_id=str(m.document_id), content_hash=m.content_hash, blob_ref=m.blob_ref,
        version_number=m.version_number, created_by=m.created_by, created_at=m.created_at,
    )


def _chunk_to_domain(m: models.Chunk) -> ChunkRecord:
    return ChunkRecord(
        id=str(m.id), document_version_id=str(m.document_version_id), content=m.content,
        chunk_index=m.chunk_index, policy_tags=list(m.policy_tags or []), token_count=m.token_count,
    )


def _policy_tag_to_domain(m: models.PolicyTag) -> PolicyTagRecord:
    return PolicyTagRecord(id=str(m.id), tenant_id=m.tenant_id, name=m.name, description=m.description)


class SQLAlchemyKnowledgeBaseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_document(self, record: DocumentRecord) -> DocumentRecord:
        m = models.Document(
            id=record.id, tenant_id=record.tenant_id, title=record.title, source_type=record.source_type.value,
            current_version_id=record.current_version_id, status=record.status.value,
            staleness_threshold_days=record.staleness_threshold_days, last_reviewed_at=record.last_reviewed_at,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _document_to_domain(m)

    async def get_document(self, document_id: str) -> DocumentRecord | None:
        m = await self.session.get(models.Document, document_id)
        return _document_to_domain(m) if m else None

    async def update_document(self, record: DocumentRecord) -> DocumentRecord:
        m = await self.session.get(models.Document, record.id)
        if m is None:
            raise LookupError(record.id)
        m.title = record.title
        m.current_version_id = record.current_version_id
        m.status = record.status.value
        m.staleness_threshold_days = record.staleness_threshold_days
        m.last_reviewed_at = record.last_reviewed_at
        await self.session.commit()
        await self.session.refresh(m)
        return _document_to_domain(m)

    async def list_stale_candidates(self, tenant_id: str) -> list[DocumentRecord]:
        return await self.list_documents(tenant_id)

    async def list_documents(self, tenant_id: str) -> list[DocumentRecord]:
        rows = await self.session.execute(select(models.Document).where(models.Document.tenant_id == tenant_id))
        return [_document_to_domain(m) for m in rows.scalars().all()]

    async def create_version(self, record: DocumentVersionRecord) -> DocumentVersionRecord:
        m = models.DocumentVersion(
            id=record.id, document_id=record.document_id, content_hash=record.content_hash,
            blob_ref=record.blob_ref, version_number=record.version_number, created_by=record.created_by,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _version_to_domain(m)

    async def get_version(self, version_id: str) -> DocumentVersionRecord | None:
        m = await self.session.get(models.DocumentVersion, version_id)
        return _version_to_domain(m) if m else None

    async def list_versions(self, document_id: str) -> list[DocumentVersionRecord]:
        rows = await self.session.execute(
            select(models.DocumentVersion).where(models.DocumentVersion.document_id == document_id)
        )
        return [_version_to_domain(m) for m in rows.scalars().all()]

    async def find_version_by_content_hash(
        self, document_id: str, content_hash: str
    ) -> DocumentVersionRecord | None:
        rows = await self.session.execute(
            select(models.DocumentVersion).where(
                models.DocumentVersion.document_id == document_id,
                models.DocumentVersion.content_hash == content_hash,
            )
        )
        m = rows.scalars().first()
        return _version_to_domain(m) if m else None

    async def create_chunks(self, records: list[ChunkRecord]) -> list[ChunkRecord]:
        models_list = [
            models.Chunk(
                id=r.id, document_version_id=r.document_version_id, content=r.content,
                chunk_index=r.chunk_index, policy_tags=r.policy_tags, token_count=r.token_count,
            )
            for r in records
        ]
        self.session.add_all(models_list)
        await self.session.commit()
        for m in models_list:
            await self.session.refresh(m)
        return [_chunk_to_domain(m) for m in models_list]

    async def list_chunks_by_version(self, document_version_id: str) -> list[ChunkRecord]:
        rows = await self.session.execute(
            select(models.Chunk)
            .where(models.Chunk.document_version_id == document_version_id)
            .order_by(models.Chunk.chunk_index)
        )
        return [_chunk_to_domain(m) for m in rows.scalars().all()]

    async def list_chunks_by_policy_tag(self, tenant_id: str, policy_tag: str) -> list[ChunkRecord]:
        doc_rows = await self.session.execute(
            select(models.Document.id).where(models.Document.tenant_id == tenant_id)
        )
        document_ids = {str(d) for d in doc_rows.scalars().all()}
        if not document_ids:
            return []
        version_rows = await self.session.execute(
            select(models.DocumentVersion.id).where(models.DocumentVersion.document_id.in_(document_ids))
        )
        version_ids = {str(v) for v in version_rows.scalars().all()}
        if not version_ids:
            return []
        chunk_rows = await self.session.execute(
            select(models.Chunk).where(models.Chunk.document_version_id.in_(version_ids))
        )
        return [_chunk_to_domain(m) for m in chunk_rows.scalars().all() if policy_tag in (m.policy_tags or [])]

    async def create_policy_tag(self, record: PolicyTagRecord) -> PolicyTagRecord:
        m = models.PolicyTag(id=record.id, tenant_id=record.tenant_id, name=record.name, description=record.description)
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _policy_tag_to_domain(m)

    async def list_policy_tags(self, tenant_id: str) -> list[PolicyTagRecord]:
        rows = await self.session.execute(select(models.PolicyTag).where(models.PolicyTag.tenant_id == tenant_id))
        return [_policy_tag_to_domain(m) for m in rows.scalars().all()]
