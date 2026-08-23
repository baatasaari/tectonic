"""HTTP adapters for this module's external dependencies. The Vector DB
and Graph DB clients target the real Module 10/11 API surfaces (this
platform now has both built), not invented endpoints.

**Known gap.** Module 11 (Graph DB)'s own LLD doesn't define a delete
endpoint yet, so `HTTPGraphDBClient.delete_by_source_ref` is a best-
effort call to a plausible-but-not-yet-real `DELETE /v1/graph-db/nodes`
— see the module README's "Design notes vs. the LLD" for the erasure-
completeness implication.
"""
from __future__ import annotations

import httpx

from long_term_memory.core.ports import GraphHit, VectorHit
from long_term_memory.telemetry.logging import get_logger

logger = get_logger(component="http_clients")


class HTTPVectorDBClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30.0)

    async def index(self, *, content: str, tenant_id: str, source_ref: str) -> str:
        resp = await self._client.post(
            "/v1/vector-db/points",
            json={
                "tenant_id": tenant_id, "source_module": "long_term_memory", "source_ref": source_ref,
                "content": content,
            },
        )
        resp.raise_for_status()
        return resp.json()["id"]

    async def search(self, *, query: str, tenant_id: str, top_k: int) -> list[VectorHit]:
        resp = await self._client.post(
            "/v1/vector-db/query", json={"tenant_id": tenant_id, "text": query, "top_k": top_k, "hybrid": False},
        )
        resp.raise_for_status()
        return [
            VectorHit(ref=r["id"], content=r.get("payload", {}).get("content", ""), score=r["score"])
            for r in resp.json()["results"]
        ]

    async def delete(self, point_id: str, tenant_id: str) -> None:
        resp = await self._client.delete(f"/v1/vector-db/points/{point_id}", params={"tenant_id": tenant_id})
        resp.raise_for_status()


class HTTPGraphDBClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30.0)

    async def create_node(self, *, name: str, tenant_id: str, source_ref: str) -> str:
        resp = await self._client.post(
            "/v1/graph-db/nodes",
            json={"entity_type": "long_term_memory_item", "name": name, "attributes": {"source_ref": source_ref}},
            headers={"X-Tenant-Id": tenant_id},
        )
        resp.raise_for_status()
        return resp.json()["id"]

    async def query_related(self, *, node_id: str, tenant_id: str) -> list[GraphHit]:
        resp = await self._client.post(
            "/v1/graph-db/query",
            json={"query_type": "neighbours", "node_id": node_id, "depth": 1},
            headers={"X-Tenant-Id": tenant_id},
        )
        resp.raise_for_status()
        return [GraphHit(ref=n["id"], name=n["name"]) for n in resp.json()["nodes"] if n["id"] != node_id]

    async def delete_by_source_ref(self, *, tenant_id: str, source_ref: str) -> None:
        try:
            resp = await self._client.request(
                "DELETE", "/v1/graph-db/nodes", params={"source_ref": source_ref}, headers={"X-Tenant-Id": tenant_id},
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("graph_db_delete_unsupported", source_ref=source_ref, error=str(e))


class HTTPLLMGatewayClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30.0)

    async def reflect(self, context: str, tenant_id: str) -> str:
        resp = await self._client.post("/v1/reflect", json={"context": context, "tenant_id": tenant_id})
        resp.raise_for_status()
        return resp.json()["reflection"]


class HTTPGuardrailsClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def check_visibility(self, *, scope: str, requesting_agent: str, policy_ref: str) -> bool:
        resp = await self._client.post(
            "/v1/guardrails/check-visibility",
            json={"scope": scope, "requesting_agent": requesting_agent, "policy_ref": policy_ref},
        )
        resp.raise_for_status()
        return resp.json()["allowed"]
