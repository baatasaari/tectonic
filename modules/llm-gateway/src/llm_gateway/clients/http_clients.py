"""HTTP adapters for Secrets and Credential Management and the Evaluation
Framework's quality-score feed's origin — point at the dependency-stub
service until those modules are deployed for real.
"""
from __future__ import annotations

import httpx


class HTTPSecretsClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=5.0)

    async def get_provider_api_key(self, provider: str, tenant_id: str) -> str:
        resp = await self._client.get("/v1/secrets/provider-key", params={"provider": provider, "tenant_id": tenant_id})
        resp.raise_for_status()
        return resp.json()["api_key"]
