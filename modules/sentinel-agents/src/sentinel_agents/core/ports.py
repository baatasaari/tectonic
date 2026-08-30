"""Abstract ports this module depends on: persistence, and the
intervention targets/escalation destinations the Decision Engine calls
into (LLD: "reuses existing control points instead of building parallel
intervention machinery")."""
from __future__ import annotations

from typing import Any, Protocol

from sentinel_agents.core.domain import (
    AgentBaselineRecord,
    AlertRecord,
    InterventionRecord,
    SwarmCorrelationWindowRecord,
)


class SentinelRepository(Protocol):
    async def get_baseline(self, tenant_id: str, agent_ref: str, action_type: str) -> AgentBaselineRecord | None: ...

    async def upsert_baseline(self, tenant_id: str, record: AgentBaselineRecord) -> AgentBaselineRecord: ...

    async def list_baselines_for_agent(self, tenant_id: str, agent_ref: str) -> list[AgentBaselineRecord]:
        """Deliberately NOT limit/offset paginated: `upsert_baseline` keys rows by
        (tenant_id, agent_ref, action_type), so this list is bounded by the number of
        distinct action types one agent performs — a small, fixed-size set, not a
        growing history — one baseline row updated in place per action_type, never
        appended to. See README "Design notes vs. the LLD" for the same reasoning."""
        ...

    async def create_alert(self, record: AlertRecord) -> AlertRecord: ...

    async def get_alert(self, tenant_id: str, alert_id: str) -> AlertRecord | None: ...

    async def update_alert(self, record: AlertRecord) -> AlertRecord: ...

    async def list_alerts(
        self, tenant_id: str, severity: str | None = None, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AlertRecord], int]: ...

    async def create_intervention_record(self, record: InterventionRecord) -> InterventionRecord: ...

    async def create_swarm_window(self, record: SwarmCorrelationWindowRecord) -> SwarmCorrelationWindowRecord: ...


class WorkflowEngineClient(Protocol):
    async def pause(self, instance_id: str, reason: str) -> None: ...

    async def terminate(self, instance_id: str, reason: str) -> None: ...


class ToolOrchestrationClient(Protocol):
    async def circuit_break(self, tool_ref: str, reason: str) -> None: ...


class HumanOversightClient(Protocol):
    async def escalate(self, context: dict[str, Any]) -> str:
        """Raises an oversight request, returns the request id."""
        ...


class AuditabilityClient(Protocol):
    async def emit(self, event: dict[str, Any]) -> None: ...
