"""Migration Manager (LLD §2 sub-components, §Level 3 "Sequence: zero-
downtime embedding model migration") — the module's differentiator
feature.

**Zero-downtime mechanism.** `VectorService` never writes to or queries a
bare Qdrant collection name — every operation goes through a Qdrant
*alias* (see `core/qdrant_ops.py`). A migration creates a brand-new
physical collection sized for the new model's dimensionality, re-embeds
every point from the current collection into it in batches (a shadow
write — the old collection keeps serving live queries the entire time),
spot-checks a sample of the migrated points, then atomically repoints the
alias from the old collection to the new one in a single
`update_collection_aliases` call. Only after that verified cutover is the
old collection pruned. This is the standard Qdrant-recommended pattern
for reindexing without downtime, and is what makes a real embedding-
model-dimension change (not just a same-dimension model swap) safe: Qdrant
fixes a named vector's dimensionality at collection-creation time, so an
in-place resize is not an option.

**Bookkeeping.** The LLD's own data model table is explicitly "Qdrant
collection schema, not a separate relational model" — it doesn't name a
migration-tracking entity. `MigrationRecord` (`core/domain.py`) is the
minimal state this manager needs to report `GET /migrations/{id}`
progress; `core/fakes.py`'s `InMemoryMigrationRepository` is this
module's default and only implementation for now, so migration state
lives for the lifetime of the owning process — acceptable given the LLD
itself describes migrations as orchestrated by Workflow Engine, which
already owns durable job tracking for long-running background work.
"""
from __future__ import annotations

from qdrant_client import AsyncQdrantClient, models

from vector_db.core import qdrant_ops, sparse_encoder
from vector_db.core.domain import (
    MigrationNotFoundError,
    MigrationRecord,
    MigrationStatus,
    new_id,
    now,
)
from vector_db.core.ports import EmbeddingProvider, MigrationRepository
from vector_db.core.qdrant_ops import DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME


class MigrationManager:
    def __init__(
        self,
        client: AsyncQdrantClient,
        embeddings: EmbeddingProvider,
        repository: MigrationRepository,
        base_alias: str,
        tenancy_model: str,
        batch_size: int,
        verification_sample_rate: float,
    ) -> None:
        self._client = client
        self._embeddings = embeddings
        self._repository = repository
        self._base_alias = base_alias
        self._tenancy_model = tenancy_model
        self._batch_size = batch_size
        self._verification_sample_rate = verification_sample_rate

    def _alias(self, tenant_id: str) -> str:
        return qdrant_ops.alias_for_tenant(self._base_alias, self._tenancy_model, tenant_id)

    async def start(self, tenant_id: str, new_embedding_model: str) -> MigrationRecord:
        alias = self._alias(tenant_id)
        source = await qdrant_ops.resolve_alias(self._client, alias)

        if source is None:
            record = MigrationRecord(
                id=new_id(), tenant_id=tenant_id, source_collection="", target_collection="",
                target_embedding_model=new_embedding_model, status=MigrationStatus.COMPLETED,
                points_total=0, points_migrated=0, completed_at=now(),
            )
            return await self._repository.create(record)

        total = (await self._client.count(source)).count
        target = f"{alias}__{new_id().split('-')[0]}"
        record = MigrationRecord(
            id=new_id(), tenant_id=tenant_id, source_collection=source, target_collection=target,
            target_embedding_model=new_embedding_model, status=MigrationStatus.RUNNING,
            points_total=total, points_migrated=0,
        )
        return await self._repository.create(record)

    async def run(self, migration_id: str) -> MigrationRecord:
        record = await self._repository.get(migration_id)
        if record is None:
            raise MigrationNotFoundError(migration_id)
        if record.status != MigrationStatus.RUNNING or not record.source_collection:
            return record

        target_created = False
        offset = None
        while True:
            points, next_offset = await self._client.scroll(
                record.source_collection, limit=self._batch_size, offset=offset, with_payload=True,
            )
            if not points:
                break

            new_points = []
            for point in points:
                content = (point.payload or {}).get("content", "")
                new_vector = await self._embeddings.embed(content, model=record.target_embedding_model, tenant_id=record.tenant_id)
                if not target_created:
                    await qdrant_ops.ensure_collection(self._client, record.target_collection, len(new_vector))
                    target_created = True
                sparse = sparse_encoder.encode(content)
                new_payload = dict(point.payload or {})
                new_payload["embedding_model_version"] = record.target_embedding_model
                new_points.append(
                    models.PointStruct(
                        id=point.id,
                        vector={
                            DENSE_VECTOR_NAME: new_vector,
                            SPARSE_VECTOR_NAME: models.SparseVector(indices=sparse.indices, values=sparse.values),
                        },
                        payload=new_payload,
                    )
                )

            await self._client.upsert(record.target_collection, points=new_points)
            record.points_migrated += len(new_points)
            record = await self._repository.update(record)

            if next_offset is None:
                break
            offset = next_offset

        await self._verify(record)

        alias = self._alias(record.tenant_id)
        await self._client.update_collection_aliases(
            change_aliases_operations=[
                models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias)),
                models.CreateAliasOperation(
                    create_alias=models.CreateAlias(collection_name=record.target_collection, alias_name=alias)
                ),
            ]
        )
        await self._client.delete_collection(record.source_collection)

        record.status = MigrationStatus.COMPLETED
        record.completed_at = now()
        return await self._repository.update(record)

    async def _verify(self, record: MigrationRecord) -> None:
        if record.points_total == 0:
            return
        sample_size = max(1, round(record.points_total * self._verification_sample_rate))
        points, _ = await self._client.scroll(record.target_collection, limit=sample_size, with_vectors=True)
        for point in points:
            vectors = point.vector or {}
            if not vectors.get(DENSE_VECTOR_NAME):
                raise RuntimeError(f"migration verification failed: point {point.id} missing dense vector")

    async def get(self, migration_id: str) -> MigrationRecord:
        record = await self._repository.get(migration_id)
        if record is None:
            raise MigrationNotFoundError(migration_id)
        return record
