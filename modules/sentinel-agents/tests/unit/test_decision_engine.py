from sentinel_agents.config import AutonomyLevelConfig
from sentinel_agents.core.decision_engine import DecisionOutcome, decide
from sentinel_agents.core.domain import AlertRecord, AlertType, Severity, new_id


def _alert(alert_type: AlertType, severity: Severity) -> AlertRecord:
    return AlertRecord(
        id=new_id(), tenant_id="t1", alert_type=alert_type, agent_refs=["a"], severity=severity, description="x",
    )


def test_swarm_always_escalates_even_if_config_would_allow_autonomous():
    config = AutonomyLevelConfig(high_severity="autonomous_intervention")
    outcome = decide(_alert(AlertType.SWARM, Severity.HIGH), config, swarm_always_escalate=True)
    assert outcome == DecisionOutcome.ESCALATE


def test_single_agent_high_severity_autonomous_by_default():
    config = AutonomyLevelConfig()
    outcome = decide(_alert(AlertType.SINGLE_AGENT, Severity.HIGH), config, swarm_always_escalate=True)
    assert outcome == DecisionOutcome.AUTONOMOUS


def test_single_agent_low_severity_alert_only_by_default():
    config = AutonomyLevelConfig()
    outcome = decide(_alert(AlertType.SINGLE_AGENT, Severity.LOW), config, swarm_always_escalate=True)
    assert outcome == DecisionOutcome.ALERT_ONLY


def test_tenant_can_restrict_high_severity_to_alert_only():
    config = AutonomyLevelConfig(high_severity="alert_only")
    outcome = decide(_alert(AlertType.SINGLE_AGENT, Severity.HIGH), config, swarm_always_escalate=True)
    assert outcome == DecisionOutcome.ALERT_ONLY
