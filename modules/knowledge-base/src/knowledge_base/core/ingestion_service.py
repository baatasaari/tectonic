"""Ingestion Service — the orchestrator tying together parsing, version
control, chunking and policy tagging, then handing chunks off to Vector
DB and Graph DB (LLD §Level 3 "Sequence: document ingestion and chunk
propagation").
"""
from __future__ import annotations

from knowledge_base.config import ChunkingConfig, StalenessConfig
from knowledge_base.core import chunker, parser, policy_tagger, staleness_monitor, version_manager
from knowledge_base.core.domain import (
    ChunkRecord,
    DocumentNotFoundError,
    DocumentRecord,
    DocumentStatus,
    DocumentVersionRecord,
    IngestionResult,
    SourceType,
    new_id,
    now,
)
from knowledge_base.core.ports import (
    BlobStorage,
    GraphDBClient,
    KnowledgeBaseRepository,
    VectorDBClient,
)
from knowledge_base.core.staleness_monitor import StalenessReport
from knowledge_base.core.tokenization import SimpleTokenCounter, TokenCounter


class IngestionService:
    def __init__(
        self,
        repository: KnowledgeBaseRepository,
        blob_storage: BlobStorage,
        vector_db: VectorDBClient,
        graph_db: GraphDBClient,
        chunking_config: ChunkingConfig,
        staleness_config: StalenessConfig,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self._repository = repository
        self._blob_storage = blob_storage
        self._vector_db = vector_db
        self._graph_db = graph_db
        self._chunking_config = chunking_config
        self._staleness_config = staleness_config
        self._token_counter = token_counter or SimpleTokenCounter()

    async def _chunk_and_propagate(
        self, *, document: DocumentRecord, version: DocumentVersionRecord, content: bytes, content_type: str,
        filename: str, policy_tags: list[str], chunk_overrides: dict[int, list[str]] | None, strategy: str | None,
    ) -> int:
        parsed = parser.parse(content, content_type, filename)
        active_strategy = strategy or self._chunking_config.default_strategy
        chunk_texts = chunker.chunk(
            parsed.text, active_strategy, parsed.headings, self._chunking_config.default_chunk_size_tokens,
            self._chunking_config.overlap_tokens, self._token_counter,
        )
        tags_per_chunk = policy_tagger.tag_chunks(len(chunk_texts), policy_tags, chunk_overrides)
        chunk_records = [
            ChunkRecord(
                id=new_id(), document_version_id=version.id, content=text, chunk_index=i,
                policy_tags=tags_per_chunk[i], token_count=self._token_counter.count(text),
            )
            for i, text in enumerate(chunk_texts)
        ]
        chunk_records = await self._repository.create_chunks(chunk_records)

        if chunk_records:
            payload = [
                {
                    "chunk_id": c.id, "content": c.content, "policy_tags": c.policy_tags,
                    "document_id": document.id, "document_version_id": version.id,
                    "tenant_id": document.tenant_id,
                }
                for c in chunk_records
            ]
            await self._vector_db.embed_and_store(payload)
            await self._graph_db.extract_entities(payload)

        return len(chunk_records)

    async def ingest_document(
        self, *, tenant_id: str, title: str, source_type: SourceType, content: bytes, content_type: str = "text/plain",
        filename: str = "", policy_tags: list[str] | None = None, chunk_overrides: dict[int, list[str]] | None = None,
        created_by: str = "", chunking_strategy: str | None = None, staleness_threshold_days: int | None = None,
    ) -> IngestionResult:
        document = DocumentRecord(
            id=new_id(), tenant_id=tenant_id, title=title, source_type=source_type,
            staleness_threshold_days=staleness_threshold_days,
        )
        document = await self._repository.create_document(document)

        blob_ref = await self._blob_storage.put(content)
        version = DocumentVersionRecord(
            id=new_id(), document_id=document.id, content_hash=version_manager.content_hash(content),
            blob_ref=blob_ref, version_number=1, created_by=created_by,
        )
        version = await self._repository.create_version(version)

        document.current_version_id = version.id
        document = await self._repository.update_document(document)

        chunk_count = await self._chunk_and_propagate(
            document=document, version=version, content=content, content_type=content_type, filename=filename,
            policy_tags=policy_tags or [], chunk_overrides=chunk_overrides, strategy=chunking_strategy,
        )
        return IngestionResult(document=document, version=version, chunk_count=chunk_count)

    async def create_version(
        self, document_id: str, *, content: bytes, content_type: str = "text/plain", filename: str = "",
        policy_tags: list[str] | None = None, chunk_overrides: dict[int, list[str]] | None = None,
        created_by: str = "", chunking_strategy: str | None = None,
    ) -> IngestionResult:
        document = await self._repository.get_document(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)

        content_hash = version_manager.content_hash(content)
        duplicate = await self._repository.find_version_by_content_hash(document_id, content_hash)
        if duplicate is not None:
            _, chunk_count = await self._repository.list_chunks_by_version(duplicate.id)
            return IngestionResult(document=document, version=duplicate, chunk_count=chunk_count)

        existing_versions = await self._repository.list_versions(document_id)
        blob_ref = await self._blob_storage.put(content)
        version = DocumentVersionRecord(
            id=new_id(), document_id=document_id, content_hash=content_hash, blob_ref=blob_ref,
            version_number=version_manager.next_version_number(existing_versions), created_by=created_by,
        )
        version = await self._repository.create_version(version)

        document.current_version_id = version.id
        document.last_reviewed_at = now()
        document.status = DocumentStatus.ACTIVE
        document = await self._repository.update_document(document)

        chunk_count = await self._chunk_and_propagate(
            document=document, version=version, content=content, content_type=content_type, filename=filename,
            policy_tags=policy_tags or [], chunk_overrides=chunk_overrides, strategy=chunking_strategy,
        )
        return IngestionResult(document=document, version=version, chunk_count=chunk_count)

    async def review(self, document_id: str, reviewed_by: str) -> DocumentRecord:
        document = await self._repository.get_document(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        document.last_reviewed_at = now()
        if document.status == DocumentStatus.STALE:
            document.status = DocumentStatus.ACTIVE
        return await self._repository.update_document(document)

    async def run_staleness_sweep(self, tenant_id: str) -> StalenessReport:
        if not self._staleness_config.auto_flag_enabled:
            return StalenessReport(stale_document_ids=[], total_active_or_stale=0)

        documents = await self._repository.list_documents(tenant_id)
        report = staleness_monitor.evaluate(documents, self._staleness_config.default_threshold_days)
        by_id = {d.id: d for d in documents}
        for document_id in report.stale_document_ids:
            document = by_id[document_id]
            if document.status == DocumentStatus.ACTIVE:
                document.status = DocumentStatus.STALE
                await self._repository.update_document(document)
        return report
