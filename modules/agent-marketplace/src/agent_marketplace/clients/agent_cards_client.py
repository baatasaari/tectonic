"""HTTP adapter for Agent Cards (Module 23) -- this module's one real
platform-peer dependency. Reads that module's own `GET
/agent-cards/{id}`, the exact card the Catalogue Sync Service snapshots.

`HTTPAgentCardsClient` is a `ResilientHTTPClient` (retry + circuit
breaker on every outbound call — see resilience.py) carrying this
platform's service-to-service JWT (`ServiceBearerAuth`), since Agent
Cards is a genuine platform peer, not a third party.
"""
from __future__ import annotations

from typing import Any

import httpx

from agent_marketplace.clients.resilience import ResilientHTTPClient
from agent_marketplace.security.jwt_auth import ServiceBearerAuth

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


class HTTPAgentCardsClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="agent-cards", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="agent-cards", auth=auth)

    async def get_card(self, card_id: str) -> dict[str, Any] | None:
        resp = await self._get_optional(f"/v1/agent-cards/{card_id}")
        return resp.json() if resp is not None else None
