"""HTTP adapter for the LLM Gateway fallback dependency (Module 3).

`HTTPLLMGatewayClient` is a `ResilientHTTPClient` (retry + circuit breaker
on every outbound call — see resilience.py).
"""
from __future__ import annotations

from typing import Any

import httpx

from intent_detection.clients.resilience import ResilientHTTPClient
from intent_detection.security.jwt_auth import ServiceBearerAuth


class HTTPLLMGatewayClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="llm-gateway", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, breaker_name="llm-gateway", auth=auth)

    async def classify_structured(
        self, *, text: str, taxonomy: list[dict[str, Any]], tenant_id: str
    ) -> list[dict[str, Any]]:
        resp = await self._post("/v1/classify-structured", json={"text": text, "taxonomy": taxonomy, "tenant_id": tenant_id})
        return resp.json()["intents"]
