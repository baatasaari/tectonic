"""HTTP adapters for this module's intervention targets and escalation
destination. Workflow Engine's pause/terminate client targets Module 1's
real, already-built API surface. Tool Orchestration's circuit-break
client is a known gap: Module 4's own LLD never defines an externally
triggerable circuit-break endpoint (its circuit breaker only opens from
call failures observed internally) — see the module README.
"""
from __future__ import annotations

from typing import Any

import httpx

from sentinel_agents.telemetry.logging import get_logger

logger = get_logger(component="http_clients")


class HTTPWorkflowEngineClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def pause(self, instance_id: str, reason: str) -> None:
        resp = await self._client.post(f"/v1/workflow-engine/instances/{instance_id}/pause", json={"reason": reason})
        resp.raise_for_status()

    async def terminate(self, instance_id: str, reason: str) -> None:
        resp = await self._client.post(
            f"/v1/workflow-engine/instances/{instance_id}/terminate", json={"reason": reason}
        )
        resp.raise_for_status()


class HTTPToolOrchestrationClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def circuit_break(self, tool_ref: str, reason: str) -> None:
        try:
            resp = await self._client.post(
                "/v1/tool-orchestration/circuit-breaker/force-open", json={"tool_ref": tool_ref, "reason": reason},
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("tool_orchestration_circuit_break_unsupported", tool_ref=tool_ref, error=str(e))


class HTTPHumanOversightClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def escalate(self, context: dict[str, Any]) -> str:
        resp = await self._client.post(
            "/v1/human-oversight/requests",
            json={
                "tenant_id": context.get("tenant_id", ""), "requesting_module": "sentinel_agents",
                "requesting_ref": context.get("alert_id", ""), "context": context, "priority": "high",
            },
        )
        resp.raise_for_status()
        return resp.json()["id"]


class HTTPAuditabilityClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=5.0)

    async def emit(self, event: dict[str, Any]) -> None:
        await self._client.post("/v1/auditability/events", json=event)
