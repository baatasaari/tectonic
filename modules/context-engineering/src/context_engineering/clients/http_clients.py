"""HTTP adapters for LLM Gateway (Module 3) and the Evaluation Framework
feedback feed. Point at the dependency-stub service until Evaluation
Framework is deployed for real.

Every client below is a `ResilientHTTPClient` (retry + circuit breaker on
every outbound call — see resilience.py).
"""
from __future__ import annotations

import httpx

class HTTPLLMGatewayClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="llm-gateway", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, breaker_name="llm-gateway", auth=auth)

    async def summarise(self, *, content: str, target_tokens: int, tenant_id: str) -> str:
        resp = await self._post("/v1/summarise", json={"content": content, "target_tokens": target_tokens, "tenant_id": tenant_id})
        return resp.json()["summary"]


class HTTPEvaluationFeedbackClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="evaluation-framework", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="evaluation-framework", auth=auth)

    async def get_feature_feedback(self, *, tenant_id: str, task_type: str) -> dict[str, float]:
        resp = await self._get("/v1/evaluation/feature-feedback", params={"tenant_id": tenant_id, "task_type": task_type})
        return resp.json()["feedback"]
