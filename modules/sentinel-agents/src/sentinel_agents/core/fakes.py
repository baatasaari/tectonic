"""In-memory fakes for the ports in core/ports.py — the unit-test tier,
mirroring the other modules' core/fakes.py.
"""
from __future__ import annotations

import copy
from typing import Any

from sentinel_agents.core.domain import (
    AgentBaselineRecord,
    AlertRecord,
    InterventionRecord,
    SwarmCorrelationWindowRecord,
)


class InMemorySentinelRepository:
    def __init__(self) -> None:
        self.baselines: dict[tuple[str, str, str], AgentBaselineRecord] = {}
        self.alerts: dict[str, AlertRecord] = {}
        self.intervention_records: list[InterventionRecord] = []
        self.swarm_windows: list[SwarmCorrelationWindowRecord] = []

    async def get_baseline(self, tenant_id: str, agent_ref: str, action_type: str) -> AgentBaselineRecord | None:
        rec = self.baselines.get((tenant_id, agent_ref, action_type))
        return copy.deepcopy(rec) if rec else None

    async def upsert_baseline(self, tenant_id: str, record: AgentBaselineRecord) -> AgentBaselineRecord:
        self.baselines[(tenant_id, record.agent_ref, record.action_type)] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def list_baselines_for_agent(self, tenant_id: str, agent_ref: str) -> list[AgentBaselineRecord]:
        return [
            copy.deepcopy(b) for (t, a, _), b in self.baselines.items() if t == tenant_id and a == agent_ref
        ]

    async def create_alert(self, record: AlertRecord) -> AlertRecord:
        self.alerts[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_alert(self, tenant_id: str, alert_id: str) -> AlertRecord | None:
        rec = self.alerts.get(alert_id)
        if rec is None or rec.tenant_id != tenant_id:
            return None
        return copy.deepcopy(rec)

    async def update_alert(self, record: AlertRecord) -> AlertRecord:
        self.alerts[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def list_alerts(self, tenant_id: str, severity: str | None = None) -> list[AlertRecord]:
        return [
            copy.deepcopy(a) for a in self.alerts.values()
            if a.tenant_id == tenant_id and (severity is None or a.severity.value == severity)
        ]

    async def create_intervention_record(self, record: InterventionRecord) -> InterventionRecord:
        self.intervention_records.append(copy.deepcopy(record))
        return copy.deepcopy(record)

    async def create_swarm_window(self, record: SwarmCorrelationWindowRecord) -> SwarmCorrelationWindowRecord:
        self.swarm_windows.append(copy.deepcopy(record))
        return copy.deepcopy(record)


class StubWorkflowEngineClient:
    def __init__(self) -> None:
        self.paused: list[tuple[str, str]] = []
        self.terminated: list[tuple[str, str]] = []

    async def pause(self, instance_id: str, reason: str) -> None:
        self.paused.append((instance_id, reason))

    async def terminate(self, instance_id: str, reason: str) -> None:
        self.terminated.append((instance_id, reason))


class StubToolOrchestrationClient:
    def __init__(self) -> None:
        self.circuit_broken: list[tuple[str, str]] = []

    async def circuit_break(self, tool_ref: str, reason: str) -> None:
        self.circuit_broken.append((tool_ref, reason))


class StubHumanOversightClient:
    def __init__(self) -> None:
        self.escalations: list[dict[str, Any]] = []

    async def escalate(self, context: dict[str, Any]) -> str:
        self.escalations.append(copy.deepcopy(context))
        return f"request-{len(self.escalations)}"


class StubAuditabilityClient:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(self, event: dict[str, Any]) -> None:
        self.events.append(copy.deepcopy(event))
