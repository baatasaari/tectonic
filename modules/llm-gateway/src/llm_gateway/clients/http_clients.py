"""HTTP adapters for Secrets and Credential Management and the Evaluation
Framework's quality-score feed's origin — point at the dependency-stub
service until those modules are deployed for real.
"""
from __future__ import annotations

import httpx

from llm_gateway.clients.resilience import ResilientHTTPClient

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=5.0)


class HTTPSecretsClient(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="secrets")

    async def get_provider_api_key(self, provider: str, tenant_id: str) -> str:
        resp = await self._get("/v1/secrets/provider-key", params={"provider": provider, "tenant_id": tenant_id})
        return resp.json()["api_key"]
