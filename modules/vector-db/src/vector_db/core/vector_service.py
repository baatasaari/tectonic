"""Vector Service — the orchestrator behind `/v1/vector-db/points` and
`/v1/vector-db/query` (LLD §Level 3 "Sequence: hybrid query"). Every
physical collection this module writes to is reached through a Qdrant
*alias*, never a bare collection name — that indirection is what makes
`MigrationManager`'s zero-downtime cutover possible (see its module
docstring).
"""
from __future__ import annotations

from typing import Any

from qdrant_client import AsyncQdrantClient, models

from vector_db.config import IsolationConfig, QueryConfig
from vector_db.core import qdrant_ops, sparse_encoder
from vector_db.core.domain import PointNotFoundError, ScoredPointResult, new_id
from vector_db.core.ports import EmbeddingProvider
from vector_db.core.qdrant_ops import DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME


class VectorService:
    def __init__(
        self,
        client: AsyncQdrantClient,
        embeddings: EmbeddingProvider,
        base_alias: str,
        isolation: IsolationConfig,
        query_config: QueryConfig,
        default_embedding_model: str,
    ) -> None:
        self._client = client
        self._embeddings = embeddings
        self._base_alias = base_alias
        self._isolation = isolation
        self._query_config = query_config
        self._default_model = default_embedding_model

    def _alias(self, tenant_id: str) -> str:
        return qdrant_ops.alias_for_tenant(self._base_alias, self._isolation.tenancy_model, tenant_id)

    async def _ensure_initial_collection(self, alias: str, dense_dim: int) -> str:
        physical = await qdrant_ops.resolve_alias(self._client, alias)
        if physical is not None:
            return physical
        physical = f"{alias}__v1"
        await qdrant_ops.ensure_collection(self._client, physical, dense_dim)
        await self._client.update_collection_aliases(
            change_aliases_operations=[
                models.CreateAliasOperation(
                    create_alias=models.CreateAlias(collection_name=physical, alias_name=alias)
                )
            ]
        )
        return physical

    async def index_point(
        self, *, tenant_id: str, source_module: str, source_ref: str, content: str | None = None,
        vector: list[float] | None = None, payload_extra: dict[str, Any] | None = None,
        embedding_model_version: str | None = None,
    ) -> str:
        model = embedding_model_version or self._default_model
        dense = vector if vector is not None else await self._embeddings.embed(content or "", model=model)
        sparse = sparse_encoder.encode(content or "")

        alias = self._alias(tenant_id)
        physical = await self._ensure_initial_collection(alias, len(dense))

        point_id = new_id()
        payload = {
            "tenant_id": tenant_id, "source_module": source_module, "source_ref": source_ref,
            "embedding_model_version": model, "content": content or "", **(payload_extra or {}),
        }
        await self._client.upsert(
            physical,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector={
                        DENSE_VECTOR_NAME: dense,
                        SPARSE_VECTOR_NAME: models.SparseVector(indices=sparse.indices, values=sparse.values),
                    },
                    payload=payload,
                )
            ],
        )
        return point_id

    async def delete_point(self, tenant_id: str, point_id: str) -> None:
        alias = self._alias(tenant_id)
        physical = await qdrant_ops.resolve_alias(self._client, alias)
        if physical is None:
            raise PointNotFoundError(point_id)
        await self._client.delete(physical, points_selector=[point_id])

    async def query(
        self, *, tenant_id: str, text: str | None = None, vector: list[float] | None = None,
        filters: dict[str, Any] | None = None, top_k: int | None = None, hybrid: bool | None = None,
    ) -> list[ScoredPointResult]:
        alias = self._alias(tenant_id)
        physical = await qdrant_ops.resolve_alias(self._client, alias)
        if physical is None:
            return []

        limit = top_k or self._query_config.default_top_k
        use_hybrid = self._query_config.hybrid_search_default if hybrid is None else hybrid
        dense = vector if vector is not None else await self._embeddings.embed(text or "")
        filter_tenant = tenant_id if self._isolation.tenancy_model == "shared_collection_with_filter" else None
        qdrant_filter = qdrant_ops.build_filter(filter_tenant, filters)

        if use_hybrid:
            sparse = sparse_encoder.encode(text or "")
            response = await self._client.query_points(
                physical,
                prefetch=[
                    models.Prefetch(query=dense, using=DENSE_VECTOR_NAME, limit=limit * 4, filter=qdrant_filter),
                    models.Prefetch(
                        query=models.SparseVector(indices=sparse.indices, values=sparse.values),
                        using=SPARSE_VECTOR_NAME, limit=limit * 4, filter=qdrant_filter,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limit,
                query_filter=qdrant_filter,
            )
        else:
            response = await self._client.query_points(
                physical, query=dense, using=DENSE_VECTOR_NAME, limit=limit, query_filter=qdrant_filter,
            )

        return [ScoredPointResult(id=str(p.id), score=p.score, payload=dict(p.payload or {})) for p in response.points]

    async def cluster_healthy(self) -> bool:
        try:
            await self._client.get_collections()
            return True
        except Exception:
            return False
