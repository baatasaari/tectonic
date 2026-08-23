"""HTTP adapter for this module's LLM Gateway dependency (LLM-as-judge
fallback for metrics with no local heuristic)."""
from __future__ import annotations

from typing import Any

import httpx


class HTTPLLMGatewayClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30.0)

    async def judge(self, agent_output: str, metric_name: str, reference_data: dict[str, Any]) -> float:
        resp = await self._client.post(
            "/v1/judge", json={"agent_output": agent_output, "metric_name": metric_name, "reference_data": reference_data}
        )
        resp.raise_for_status()
        return float(resp.json()["score"])
