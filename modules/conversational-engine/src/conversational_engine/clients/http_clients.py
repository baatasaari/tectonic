"""HTTP adapters for this module's external dependencies: LLM Gateway,
Guardrails, Long-Term Memory, Human Oversight. Point at the dependency-stub
service until those modules are deployed for real — LLM Gateway now exists
as Module 3 in this platform, so point `dependency_stub_base_url` (or a
dedicated LLM Gateway URL, once each dependency gets its own config knob)
at its real base URL in any environment running both.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


class HTTPLLMGatewayClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30.0)

    async def stream_complete(
        self, *, prompt_context: dict[str, Any], tenant_id: str, trace_id: str
    ) -> AsyncIterator[str]:
        async with self._client.stream(
            "POST",
            "/v1/completions/stream",
            json={"context": prompt_context, "tenant_id": tenant_id},
            headers={"X-Trace-Id": trace_id},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[len("data: ") :]
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                yield chunk["text"]

    async def classify(self, *, text: str, taxonomy: list[str], tenant_id: str) -> dict[str, float]:
        resp = await self._client.post(
            "/v1/classify", json={"text": text, "taxonomy": taxonomy, "tenant_id": tenant_id}
        )
        resp.raise_for_status()
        return resp.json()["scores"]


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


class HTTPLongTermMemoryClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def recall_identity_context(self, *, user_ref: str, tenant_id: str) -> dict[str, Any] | None:
        resp = await self._client.get("/v1/memory/identity", params={"user_ref": user_ref, "tenant_id": tenant_id})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


class HTTPHumanOversightClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def request_handoff(
        self, *, session_id: str, trigger_reason: str, context: dict[str, Any], tenant_id: str
    ) -> str:
        resp = await self._client.post(
            "/v1/oversight/handoff-request",
            json={"session_id": session_id, "trigger_reason": trigger_reason, "context": context, "tenant_id": tenant_id},
        )
        resp.raise_for_status()
        return resp.json()["human_oversight_ref_id"]


class HTTPObservabilityClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=5.0)

    async def emit(self, event: dict[str, Any]) -> None:
        await self._client.post("/v1/observability/events", json=event)


class HTTPAuditabilityClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=5.0)

    async def emit(self, event: dict[str, Any]) -> None:
        await self._client.post("/v1/auditability/events", json=event)
