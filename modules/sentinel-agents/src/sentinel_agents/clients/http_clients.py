"""HTTP adapters for this module's intervention targets and escalation
destination. Workflow Engine's pause/terminate client targets Module 1's
real, already-built API surface. Tool Orchestration's circuit-break
client is a known gap: Module 4's own LLD never defines an externally
triggerable circuit-break endpoint (its circuit breaker only opens from
call failures observed internally) — see the module README.

Every client below is a `ResilientHTTPClient` (retry + circuit breaker on
every outbound call — see resilience.py).
"""
from __future__ import annotations

from typing import Any

import httpx

from sentinel_agents.clients.resilience import CircuitBreakerError, ResilientHTTPClient
from sentinel_agents.telemetry.logging import get_logger

logger = get_logger(component="http_clients")

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
_VERY_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=5.0)


class HTTPWorkflowEngineClient(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="workflow-engine")

    async def pause(self, instance_id: str, reason: str) -> None:
        await self._post(f"/v1/workflow-engine/instances/{instance_id}/pause", json={"reason": reason})

    async def terminate(self, instance_id: str, reason: str) -> None:
        await self._post(f"/v1/workflow-engine/instances/{instance_id}/terminate", json={"reason": reason})


class HTTPToolOrchestrationClient(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="tool-orchestration", fail_max=10)

    async def circuit_break(self, tool_ref: str, reason: str) -> None:
        try:
            await self._post(
                "/v1/tool-orchestration/circuit-breaker/force-open", json={"tool_ref": tool_ref, "reason": reason},
            )
        except (httpx.HTTPError, CircuitBreakerError) as e:
            logger.warning("tool_orchestration_circuit_break_unsupported", tool_ref=tool_ref, error=str(e))


class HTTPHumanOversightClient(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="human-oversight")

    async def escalate(self, context: dict[str, Any]) -> str:
        resp = await self._post(
            "/v1/human-oversight/requests",
            json={
                "tenant_id": context.get("tenant_id", ""), "requesting_module": "sentinel_agents",
                "requesting_ref": context.get("alert_id", ""), "context": context, "priority": "high",
            },
        )
        return resp.json()["id"]


class HTTPAuditabilityClient(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, timeout=_VERY_SHORT_TIMEOUT, breaker_name="auditability", fail_max=10)

    async def emit(self, event: dict[str, Any]) -> None:
        try:
            await self._post("/v1/auditability/events", json=event)
        except (httpx.HTTPError, CircuitBreakerError) as exc:
            logger.warning("auditability_emit_failed", error=str(exc))
