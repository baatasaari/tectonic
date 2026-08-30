"""Event Stream Consumer + orchestrator (LLD §2 sub-components, §Level 3
"Sequence: single-agent deviation triggering autonomous pause" and
"Sequence: swarm-level anomaly requiring human escalation"). Ties the
Behavioural Baseliner, Swarm Correlation Engine and Intervention
Decision Engine together for each incoming agent action event.

**Swarm window state.** The correlation window's recent-moderate-events
list is held in process memory, not a shared store — correct for a
single instance, but a multi-replica deployment consuming different
Kafka partitions would each see only part of the swarm signal. A shared
window (Redis, or partitioning by tenant rather than round-robin) would
be needed for production horizontal scale; out of scope here since this
module's own testability contract already runs against a single
replayed event stream, not partitioned Kafka.
"""
from __future__ import annotations

from sentinel_agents.config import SentinelAgentsSettings
from sentinel_agents.core import baseliner
from sentinel_agents.core.decision_engine import DecisionOutcome, decide
from sentinel_agents.core.domain import (
    AgentActionEvent,
    AlertRecord,
    AlertStatus,
    AlertType,
    InterventionRecord,
    InterventionType,
    Severity,
    SwarmCorrelationWindowRecord,
    new_id,
)
from sentinel_agents.core.ports import (
    AuditabilityClient,
    HumanOversightClient,
    SentinelRepository,
    ToolOrchestrationClient,
    WorkflowEngineClient,
)
from sentinel_agents.core.swarm_correlation import (
    MODERATE_Z_THRESHOLD,
    ModerateDeviationEvent,
    SwarmWindowTracker,
)

_SEVERITY_BANDS = ((6.0, Severity.HIGH), (4.0, Severity.MEDIUM))


def _severity_for_z(z: float) -> Severity:
    for threshold, severity in _SEVERITY_BANDS:
        if z >= threshold:
            return severity
    return Severity.LOW


class SentinelEventProcessor:
    def __init__(
        self,
        repository: SentinelRepository,
        workflow_engine: WorkflowEngineClient,
        tool_orchestration: ToolOrchestrationClient,
        human_oversight: HumanOversightClient,
        auditability: AuditabilityClient,
        settings: SentinelAgentsSettings,
        window_tracker: SwarmWindowTracker,
    ) -> None:
        self._repository = repository
        self._workflow_engine = workflow_engine
        self._tool_orchestration = tool_orchestration
        self._human_oversight = human_oversight
        self._auditability = auditability
        self._settings = settings
        self._window_tracker = window_tracker

    async def process(self, event: AgentActionEvent) -> AlertRecord | None:
        baseline = await self._repository.get_baseline(event.tenant_id, event.agent_ref, event.action_type)
        check = baseliner.update_and_check(
            baseline, event.agent_ref, event.action_type, event.value, self._settings.baselining.sensitivity,
        )
        await self._repository.upsert_baseline(event.tenant_id, check.baseline)

        if check.z_score >= MODERATE_Z_THRESHOLD:
            self._window_tracker.record(
                ModerateDeviationEvent(
                    agent_ref=event.agent_ref, action_type=event.action_type, z_score=check.z_score,
                    timestamp=event.timestamp,
                )
            )
        self._window_tracker.prune(event.timestamp, self._settings.swarm_detection.correlation_window_seconds)

        swarm_result = None
        if self._settings.swarm_detection.enabled:
            swarm_result = self._window_tracker.detect(
                window_seconds=self._settings.swarm_detection.correlation_window_seconds,
                min_agents=self._settings.swarm_detection.min_agents, reference_time=event.timestamp,
            )

        if swarm_result is not None:
            await self._repository.create_swarm_window(
                self._swarm_window_record(event.tenant_id, swarm_result)
            )
            alert = AlertRecord(
                id=new_id(), tenant_id=event.tenant_id, alert_type=AlertType.SWARM,
                agent_refs=swarm_result.agent_refs, severity=Severity.HIGH,
                description=swarm_result.pattern_description,
            )
            alert = await self._repository.create_alert(alert)
            await self._handle_decision(alert, event)
            return alert

        if check.deviation_detected:
            severity = _severity_for_z(check.z_score)
            alert = AlertRecord(
                id=new_id(), tenant_id=event.tenant_id, alert_type=AlertType.SINGLE_AGENT,
                agent_refs=[event.agent_ref], severity=severity,
                description=f"z-score {check.z_score:.2f} for action_type={event.action_type}",
            )
            alert = await self._repository.create_alert(alert)
            await self._handle_decision(alert, event)
            return alert

        return None

    async def _handle_decision(self, alert: AlertRecord, event: AgentActionEvent) -> None:
        outcome = decide(
            alert, self._settings.intervention.autonomy_level, self._settings.intervention.swarm_anomalies_always_escalate,
        )

        if outcome == DecisionOutcome.AUTONOMOUS:
            target_ref = event.instance_id or ""
            if event.instance_id:
                await self._workflow_engine.pause(event.instance_id, reason=f"sentinel_intervention:{alert.id}")
            await self._repository.create_intervention_record(
                InterventionRecord(
                    id=new_id(), alert_id=alert.id, intervention_type=InterventionType.PAUSE,
                    target_ref=target_ref, outcome="executed" if event.instance_id else "skipped_no_target",
                )
            )
            alert.status = AlertStatus.AUTONOMOUS_INTERVENTION
        elif outcome == DecisionOutcome.ESCALATE:
            await self._human_oversight.escalate(
                {
                    "tenant_id": event.tenant_id, "alert_id": alert.id, "alert_type": alert.alert_type.value,
                    "agent_refs": alert.agent_refs, "severity": alert.severity.value, "description": alert.description,
                }
            )
            alert.status = AlertStatus.ESCALATED_TO_HUMAN
        else:
            alert.status = AlertStatus.ALERTED

        await self._repository.update_alert(alert)
        await self._auditability.emit(
            {
                "event": "sentinel_alert", "tenant_id": event.tenant_id, "alert_id": alert.id,
                "outcome": outcome.value, "severity": alert.severity.value,
            }
        )

    @staticmethod
    def _swarm_window_record(tenant_id: str, result):
        return SwarmCorrelationWindowRecord(
            id=new_id(), tenant_id=tenant_id, window_start=result.window_start, window_end=result.window_end,
            agent_refs_involved=result.agent_refs, correlation_score=result.correlation_score,
            pattern_description=result.pattern_description,
        )
