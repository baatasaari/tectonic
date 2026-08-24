"""HTTP adapters for LLM Gateway, Guardrails, and Sentinel Agents — the
tool-synthesis dependencies — pointing at the dependency-stub service until
those modules are deployed for real. LLM Gateway now exists as Module 3.

Every client below is a `ResilientHTTPClient` (retry + circuit breaker on
every outbound call — see resilience.py).
"""
from __future__ import annotations

from typing import Any

import httpx

from tool_orchestration.clients.resilience import ResilientHTTPClient

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


class HTTPLLMGatewayClient(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, breaker_name="llm-gateway")

    async def complete(self, *, prompt_context: dict[str, Any], tenant_id: str) -> dict[str, Any]:
        resp = await self._post("/v1/completions", json={"context": prompt_context, "tenant_id": tenant_id})
        return resp.json()["proposal"]


class HTTPGuardrailsClient(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="guardrails")

    async def check(
        self, *, content: dict[str, Any], policy_profile: str, tenant_id: str
    ) -> tuple[bool, dict[str, Any]]:
        resp = await self._post(
            "/v1/guardrails/check", json={"content": content, "policy_profile": policy_profile, "tenant_id": tenant_id}
        )
        data = resp.json()
        return bool(data["allowed"]), data.get("detail", {})


class HTTPSentinelAgentsClient(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="sentinel-agents")

    async def submit_for_review(self, *, tool_id: str, proposed_schema: dict[str, Any], tenant_id: str) -> str:
        resp = await self._post(
            "/v1/sentinel/reviews",
            json={"tool_id": tool_id, "proposed_schema": proposed_schema, "tenant_id": tenant_id},
        )
        return resp.json()["review_id"]
