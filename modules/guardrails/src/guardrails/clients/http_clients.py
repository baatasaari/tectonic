"""HTTP adapters for this module's external dependencies: LLM Gateway
(ambiguous jailbreak classification, red-team adversarial prompt
generation) and Sentinel Agents (bypass alerting).

Every client below is a `ResilientHTTPClient` (retry + circuit breaker on
every outbound call — see resilience.py). `HTTPLLMGatewayClient`'s calls
are deliberately left to raise on final failure (not swallowed): this is
a safety gate, and silently treating "couldn't classify" as "benign"
would defeat the point.
"""
from __future__ import annotations

from typing import Any

import httpx

from guardrails.clients.resilience import CircuitBreakerError, ResilientHTTPClient
from guardrails.telemetry.logging import get_logger

logger = get_logger(component="http_clients")

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=5.0)


class HTTPLLMGatewayClient(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, breaker_name="llm-gateway")

    async def classify_intent(self, text: str, tenant_id: str) -> str:
        resp = await self._post("/v1/classify-intent", json={"text": text, "tenant_id": tenant_id})
        return resp.json()["classification"]

    async def generate_adversarial_prompts(self, count: int, tenant_id: str) -> list[str]:
        resp = await self._post("/v1/generate-adversarial-prompts", json={"count": count, "tenant_id": tenant_id})
        return resp.json()["prompts"]


class HTTPSentinelAgentsClient(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="sentinel-agents", fail_max=10)

    async def alert(self, event: dict[str, Any]) -> None:
        try:
            await self._post("/v1/sentinel-agents/external-alerts", json=event)
        except (httpx.HTTPError, CircuitBreakerError) as exc:
            logger.warning("sentinel_agents_alert_failed", error=str(exc))
