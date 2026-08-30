import math
from datetime import UTC, datetime, timedelta

from sentinel_agents.core.domain import (
    AgentActionEvent,
    AgentBaselineRecord,
    AlertRecord,
    AlertStatus,
    AlertType,
    Severity,
)

_MEAN = 10.0
_M2 = 8.0  # sample_count=10 -> variance=0.8 -> std ~= 0.894... see below, recomputed per-test as needed
_STD = math.sqrt(_M2 / 10)


async def _seed_baseline(harness, tenant_id: str, agent_ref: str, sample_count: int = 10) -> None:
    await harness.repository.upsert_baseline(
        tenant_id,
        AgentBaselineRecord(agent_ref=agent_ref, action_type="tool_call", mean=_MEAN, m2=_M2, sample_count=sample_count),
    )


def _value_for_z(z: float) -> float:
    return _MEAN + z * _STD


async def test_stable_event_produces_no_alert(harness):
    await _seed_baseline(harness, "t1", "agent-a")
    event = AgentActionEvent(tenant_id="t1", agent_ref="agent-a", action_type="tool_call", value=_MEAN)
    alert = await harness.processor.process(event)
    assert alert is None


async def test_high_severity_outlier_triggers_autonomous_pause(harness):
    await _seed_baseline(harness, "t1", "solo-agent")
    event = AgentActionEvent(
        tenant_id="t1", agent_ref="solo-agent", action_type="tool_call", value=_value_for_z(20.0),
        instance_id="wf-instance-1",
    )
    alert = await harness.processor.process(event)

    assert alert is not None
    assert alert.alert_type == AlertType.SINGLE_AGENT
    assert alert.status == AlertStatus.AUTONOMOUS_INTERVENTION
    assert harness.workflow_engine.paused == [("wf-instance-1", f"sentinel_intervention:{alert.id}")]
    assert len(harness.repository.intervention_records) == 1
    assert len(harness.auditability.events) == 1


async def test_low_severity_deviation_is_alert_only(harness):
    await _seed_baseline(harness, "t1", "agent-low")
    event = AgentActionEvent(tenant_id="t1", agent_ref="agent-low", action_type="tool_call", value=_value_for_z(3.2))
    alert = await harness.processor.process(event)

    assert alert is not None
    assert alert.status == AlertStatus.ALERTED
    assert harness.workflow_engine.paused == []
    assert harness.human_oversight.escalations == []


async def test_swarm_anomaly_escalates_to_human_not_autonomous(harness_factory):
    from sentinel_agents.config import AutonomyLevelConfig, SentinelAgentsSettings

    settings = SentinelAgentsSettings()
    settings.intervention.autonomy_level = AutonomyLevelConfig(
        low_severity="autonomous_intervention", medium_severity="autonomous_intervention",
        high_severity="autonomous_intervention",
    )
    harness = harness_factory(settings=settings)

    for agent in ("agent-a", "agent-b", "agent-c"):
        await _seed_baseline(harness, "t1", agent)

    same_time = datetime.now(UTC)
    moderate_value = _value_for_z(2.0)  # above MODERATE_Z_THRESHOLD(1.5), below medium single-agent threshold(3.0)

    alerts = []
    for agent in ("agent-a", "agent-b", "agent-c"):
        event = AgentActionEvent(
            tenant_id="t1", agent_ref=agent, action_type="tool_call", value=moderate_value, timestamp=same_time,
        )
        alerts.append(await harness.processor.process(event))

    assert alerts[0] is None
    assert alerts[1] is None
    assert alerts[2] is not None
    assert alerts[2].alert_type == AlertType.SWARM
    assert set(alerts[2].agent_refs) == {"agent-a", "agent-b", "agent-c"}
    assert alerts[2].status == AlertStatus.ESCALATED_TO_HUMAN
    # Even though this harness's autonomy config would allow autonomous
    # intervention for every severity, swarm anomalies always escalate.
    assert harness.workflow_engine.paused == []
    assert len(harness.human_oversight.escalations) == 1


async def test_swarm_detection_disabled_falls_back_to_single_agent_logic(harness_factory):
    from sentinel_agents.config import SentinelAgentsSettings

    settings = SentinelAgentsSettings()
    settings.swarm_detection.enabled = False
    harness = harness_factory(settings=settings)

    for agent in ("agent-a", "agent-b", "agent-c"):
        await _seed_baseline(harness, "t1", agent)

    moderate_value = _value_for_z(2.0)
    for agent in ("agent-a", "agent-b", "agent-c"):
        event = AgentActionEvent(tenant_id="t1", agent_ref=agent, action_type="tool_call", value=moderate_value)
        alert = await harness.processor.process(event)
        assert alert is None  # moderate deviation alone never triggers single-agent alert either


async def _make_alert(harness, tenant_id: str, *, detected_at: datetime) -> AlertRecord:
    return await harness.repository.create_alert(
        AlertRecord(
            id=f"alert-{detected_at.isoformat()}", tenant_id=tenant_id, alert_type=AlertType.SINGLE_AGENT,
            agent_refs=["agent-a"], severity=Severity.LOW, description="test alert", detected_at=detected_at,
        )
    )


async def test_list_alerts_paginates_newest_first(harness):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(3):
        await _make_alert(harness, "t1", detected_at=base + timedelta(hours=i))

    first_page, total_1 = await harness.repository.list_alerts("t1", limit=2, offset=0)
    second_page, total_2 = await harness.repository.list_alerts("t1", limit=2, offset=2)

    assert total_1 == 3
    assert total_2 == 3
    assert len(first_page) == 2
    assert len(second_page) == 1
    # newest (highest detected_at) first
    assert [a.detected_at for a in first_page] == sorted((a.detected_at for a in first_page), reverse=True)
    assert first_page[0].detected_at > first_page[1].detected_at > second_page[0].detected_at


async def test_list_alerts_empty_result_returns_zero_total(harness):
    alerts, total = await harness.repository.list_alerts("t1")
    assert alerts == []
    assert total == 0
