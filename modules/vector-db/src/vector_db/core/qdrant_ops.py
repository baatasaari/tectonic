"""Shared helpers for talking to Qdrant — collection/alias resolution and
payload filter construction, used by both `VectorService` and
`MigrationManager`.
"""
from __future__ import annotations

from typing import Any

from qdrant_client import AsyncQdrantClient, models

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


async def resolve_alias(client: AsyncQdrantClient, alias: str) -> str | None:
    """Returns the physical collection name an alias currently points to,
    or None if the alias doesn't exist yet."""
    aliases = await client.get_aliases()
    for a in aliases.aliases:
        if a.alias_name == alias:
            return a.collection_name
    return None


async def ensure_collection(client: AsyncQdrantClient, collection_name: str, dense_dim: int) -> None:
    if await client.collection_exists(collection_name):
        return
    await client.create_collection(
        collection_name,
        vectors_config={DENSE_VECTOR_NAME: models.VectorParams(size=dense_dim, distance=models.Distance.COSINE)},
        sparse_vectors_config={SPARSE_VECTOR_NAME: models.SparseVectorParams()},
    )


def build_filter(tenant_id: str | None, filters: dict[str, Any] | None) -> models.Filter | None:
    conditions: list[models.FieldCondition] = []
    if tenant_id is not None:
        conditions.append(models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id)))
    for key, value in (filters or {}).items():
        conditions.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
    if not conditions:
        return None
    return models.Filter(must=conditions)


def alias_for_tenant(base_alias: str, tenancy_model: str, tenant_id: str) -> str:
    if tenancy_model == "dedicated_collection":
        return f"{base_alias}__{tenant_id}"
    return base_alias
