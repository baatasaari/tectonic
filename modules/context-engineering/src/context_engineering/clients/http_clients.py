"""HTTP adapters for LLM Gateway (Module 3) and the Evaluation Framework
feedback feed. Point at the dependency-stub service until Evaluation
Framework is deployed for real.
"""
from __future__ import annotations

import httpx

from context_engineering.security.jwt_auth import ServiceBearerAuth


class HTTPLLMGatewayClient:
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="llm-gateway", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30.0, auth=auth)

    async def summarise(self, *, content: str, target_tokens: int, tenant_id: str) -> str:
        resp = await self._client.post(
            "/v1/summarise", json={"content": content, "target_tokens": target_tokens, "tenant_id": tenant_id}
        )
        resp.raise_for_status()
        return resp.json()["summary"]


class HTTPEvaluationFeedbackClient:
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="evaluation-framework", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=10.0, auth=auth)

    async def get_feature_feedback(self, *, tenant_id: str, task_type: str) -> dict[str, float]:
        resp = await self._client.get(
            "/v1/evaluation/feature-feedback", params={"tenant_id": tenant_id, "task_type": task_type}
        )
        resp.raise_for_status()
        return resp.json()["feedback"]
