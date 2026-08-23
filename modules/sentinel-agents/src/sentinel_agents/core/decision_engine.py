"""Intervention Decision Engine (LLD §2 sub-components): decides whether
to alert, escalate to a human, or autonomously intervene, based on
severity and tenant policy. Swarm anomalies always escalate to a human,
never autonomous — a hard rule, not tenant-configurable (LLD §Level 4
non-functional targets: "cannot be overridden to autonomous, by design").
"""
from __future__ import annotations

from enum import StrEnum

from sentinel_agents.config import AutonomyLevelConfig
from sentinel_agents.core.domain import AlertRecord, AlertType


class DecisionOutcome(StrEnum):
    ALERT_ONLY = "alert_only"
    AUTONOMOUS = "autonomous"
    ESCALATE = "escalate"


def decide(alert: AlertRecord, autonomy_config: AutonomyLevelConfig, swarm_always_escalate: bool) -> DecisionOutcome:
    if alert.alert_type == AlertType.SWARM and swarm_always_escalate:
        return DecisionOutcome.ESCALATE

    autonomy = getattr(autonomy_config, f"{alert.severity.value}_severity", "alert_only")
    if autonomy == "autonomous_intervention":
        return DecisionOutcome.AUTONOMOUS
    return DecisionOutcome.ALERT_ONLY
