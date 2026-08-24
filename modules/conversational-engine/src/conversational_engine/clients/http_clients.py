"""HTTP adapters for this module's external dependencies: LLM Gateway,
Guardrails, Long-Term Memory, Human Oversight. Point at the dependency-stub
service until those modules are deployed for real — LLM Gateway now exists
as Module 3 in this platform, so point `dependency_stub_base_url` (or a
dedicated LLM Gateway URL, once each dependency gets its own config knob)
at its real base URL in any environment running both.

Every client below is a `ResilientHTTPClient` (retry + circuit breaker on
every outbound call — see resilience.py) except `stream_complete`, which is
deliberately left unwrapped: retrying a partially-consumed SSE stream is
unsafe, so a streaming caller needs its own reconnect story if it wants one.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from conversational_engine.clients.resilience import CircuitBreakerError, ResilientHTTPClient
from conversational_engine.security.jwt_auth import ServiceBearerAuth
from conversational_engine.telemetry.logging import get_logger

logger = get_logger(component="http_clients")

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
_VERY_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=5.0)


class HTTPLLMGatewayClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="llm-gateway", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, breaker_name="llm-gateway", auth=auth)

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
        resp = await self._post("/v1/classify", json={"text": text, "taxonomy": taxonomy, "tenant_id": tenant_id})
        return resp.json()["scores"]


class HTTPGuardrailsClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="guardrails", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="guardrails", auth=auth)

    async def check(
        self, *, content: dict[str, Any], policy_profile: str, tenant_id: str
    ) -> tuple[bool, dict[str, Any]]:
        resp = await self._post(
            "/v1/guardrails/check",
            json={"content": content, "policy_profile": policy_profile, "tenant_id": tenant_id},
        )
        data = resp.json()
        return bool(data["allowed"]), data.get("detail", {})


class HTTPLongTermMemoryClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="long-term-memory", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="long-term-memory", auth=auth)

    async def recall_identity_context(self, *, user_ref: str, tenant_id: str) -> dict[str, Any] | None:
        resp = await self._get_optional("/v1/memory/identity", params={"user_ref": user_ref, "tenant_id": tenant_id})
        return resp.json() if resp is not None else None


class HTTPHumanOversightClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="human-oversight", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="human-oversight", auth=auth)

    async def request_handoff(
        self, *, session_id: str, trigger_reason: str, context: dict[str, Any], tenant_id: str
    ) -> str:
        resp = await self._post(
            "/v1/oversight/handoff-request",
            json={"session_id": session_id, "trigger_reason": trigger_reason, "context": context, "tenant_id": tenant_id},
        )
        return resp.json()["human_oversight_ref_id"]


class HTTPObservabilityClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="observability", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_VERY_SHORT_TIMEOUT, breaker_name="observability", fail_max=10, auth=auth)

    async def emit(self, event: dict[str, Any]) -> None:
        # Best-effort, as before this module had retry/breaker wiring: telemetry
        # emission must never be the reason a real request fails.
        try:
            await self._post("/v1/observability/events", json=event)
        except (httpx.HTTPError, CircuitBreakerError) as exc:
            logger.warning("observability_emit_failed", error=str(exc))


class HTTPAuditabilityClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="auditability", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_VERY_SHORT_TIMEOUT, breaker_name="auditability", fail_max=10, auth=auth)

    async def emit(self, event: dict[str, Any]) -> None:
        try:
            await self._post("/v1/auditability/events", json=event)
        except (httpx.HTTPError, CircuitBreakerError) as exc:
            logger.warning("auditability_emit_failed", error=str(exc))
