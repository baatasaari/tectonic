"""HTTP adapters for this module's external dependencies: LLM Gateway
(ambiguous jailbreak classification, red-team adversarial prompt
generation) and Sentinel Agents (bypass alerting).
"""
from __future__ import annotations

from typing import Any

import httpx

from guardrails.security.jwt_auth import ServiceBearerAuth


class HTTPLLMGatewayClient:
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="llm-gateway", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30.0, auth=auth)

    async def classify_intent(self, text: str, tenant_id: str) -> str:
        resp = await self._client.post("/v1/classify-intent", json={"text": text, "tenant_id": tenant_id})
        resp.raise_for_status()
        return resp.json()["classification"]

    async def generate_adversarial_prompts(self, count: int, tenant_id: str) -> list[str]:
        resp = await self._client.post("/v1/generate-adversarial-prompts", json={"count": count, "tenant_id": tenant_id})
        resp.raise_for_status()
        return resp.json()["prompts"]


class HTTPSentinelAgentsClient:
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="sentinel-agents", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=5.0, auth=auth)

    async def alert(self, event: dict[str, Any]) -> None:
        await self._client.post("/v1/sentinel-agents/external-alerts", json=event)
