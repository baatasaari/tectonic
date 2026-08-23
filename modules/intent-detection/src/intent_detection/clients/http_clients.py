"""HTTP adapter for the LLM Gateway fallback dependency (Module 3)."""
from __future__ import annotations

from typing import Any

import httpx


class HTTPLLMGatewayClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30.0)

    async def classify_structured(
        self, *, text: str, taxonomy: list[dict[str, Any]], tenant_id: str
    ) -> list[dict[str, Any]]:
        resp = await self._client.post(
            "/v1/classify-structured", json={"text": text, "taxonomy": taxonomy, "tenant_id": tenant_id}
        )
        resp.raise_for_status()
        return resp.json()["intents"]
