"""HTTP adapter for this module's LLM Gateway dependency (LLM-as-judge
fallback for metrics with no local heuristic, and the raw completion
primitive the real DeepEval integration in core/deepeval_adapter.py uses).

`HTTPLLMGatewayClient` is a `ResilientHTTPClient` (retry + circuit
breaker on every outbound call — see resilience.py).
"""
from __future__ import annotations

from typing import Any

import httpx

from evaluation_framework.clients.resilience import ResilientHTTPClient
from evaluation_framework.security.jwt_auth import ServiceBearerAuth


class HTTPLLMGatewayClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="llm-gateway", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, breaker_name="llm-gateway", auth=auth)

    async def judge(self, agent_output: str, metric_name: str, reference_data: dict[str, Any]) -> float:
        resp = await self._post(
            "/v1/judge", json={"agent_output": agent_output, "metric_name": metric_name, "reference_data": reference_data}
        )
        return float(resp.json()["score"])

    async def complete(self, prompt: str) -> str:
        resp = await self._post("/v1/complete", json={"prompt": prompt})
        return resp.json()["text"]
