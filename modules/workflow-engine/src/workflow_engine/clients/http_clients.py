"""HTTP adapters for the four external module dependencies this module talks
to at runtime: LLM Gateway, Tool Orchestration, Guardrails, Human Oversight.

Each of those modules is out of scope for this build (they are their own
platform modules); these clients let Workflow Engine run for real once they
exist, and point at the lightweight dependency-stub service
(../../stubs/dependency-stub) in the meantime — see deploy docker-compose.yml.
Base URLs are plain config, one per dependency, so each can point at a real
module instance or the stub independently.
"""
from __future__ import annotations

from typing import Any

import httpx


class HTTPLLMGatewayClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30.0)

    async def complete(
        self, *, agent_ref: str, prompt_context: dict[str, Any], tenant_id: str, trace_id: str
    ) -> tuple[dict[str, Any], float]:
        resp = await self._client.post(
            "/v1/completions",
            json={"agent_ref": agent_ref, "context": prompt_context, "tenant_id": tenant_id},
            headers={"X-Trace-Id": trace_id},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["response"], float(data["confidence_score"])


class HTTPToolOrchestrationClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30.0)

    async def invoke(
        self, *, tool_ref: str, arguments: dict[str, Any], tenant_id: str, trace_id: str
    ) -> dict[str, Any]:
        resp = await self._client.post(
            "/v1/tools/invoke",
            json={"tool_ref": tool_ref, "arguments": arguments, "tenant_id": tenant_id},
            headers={"X-Trace-Id": trace_id},
        )
        resp.raise_for_status()
        return resp.json()


class HTTPGuardrailsClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def check(
        self, *, content: dict[str, Any], policy_profile: str, tenant_id: str
    ) -> tuple[bool, dict[str, Any]]:
        resp = await self._client.post(
            "/v1/guardrails/check",
            json={"content": content, "policy_profile": policy_profile, "tenant_id": tenant_id},
        )
        resp.raise_for_status()
        data = resp.json()
        return bool(data["allowed"]), data.get("detail", {})


class HTTPHumanOversightClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def request_approval(
        self, *, approval_request_id: str, step_execution_id: str, context: dict[str, Any], tenant_id: str
    ) -> str:
        resp = await self._client.post(
            "/v1/oversight/requests",
            json={
                "approval_request_id": approval_request_id,
                "step_execution_id": step_execution_id,
                "context": context,
                "tenant_id": tenant_id,
            },
        )
        resp.raise_for_status()
        return resp.json()["human_oversight_ref_id"]
