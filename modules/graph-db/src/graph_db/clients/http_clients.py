"""HTTP adapter for the Auditability dependency."""
from __future__ import annotations

from typing import Any

import httpx


class HTTPAuditabilityClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=5.0)

    async def emit(self, event: dict[str, Any]) -> None:
        await self._client.post("/v1/auditability/events", json=event)
