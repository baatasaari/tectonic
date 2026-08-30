"""Behavioural Baseliner (LLD §2 sub-components): maintains per-agent
normal-behaviour statistics, flags deviation. The z-score for a new
value is computed against the baseline *before* folding the new value
in — otherwise an outlier would dampen its own deviation score by
shifting the mean/variance that scores it. The baseline still learns
from every value afterwards, including anomalous ones, so a sustained
behaviour shift is eventually absorbed as the new normal rather than
alerting forever; a min-sample floor avoids flagging on a cold start.
"""
from __future__ import annotations

from dataclasses import dataclass

from sentinel_agents.core import stats
from sentinel_agents.core.domain import AgentBaselineRecord, now
from sentinel_agents.core.stats import WelfordState

MIN_SAMPLES = 5

_SENSITIVITY_THRESHOLDS = {"low": 4.0, "medium": 3.0, "high": 2.0}


@dataclass
class BaselineCheckResult:
    baseline: AgentBaselineRecord
    deviation_detected: bool
    z_score: float


def update_and_check(
    baseline: AgentBaselineRecord | None, agent_ref: str, action_type: str, value: float, sensitivity: str,
) -> BaselineCheckResult:
    pre_state = WelfordState(baseline.mean, baseline.m2, baseline.sample_count) if baseline else WelfordState(0.0, 0.0, 0)
    has_history = pre_state.count >= MIN_SAMPLES

    z = stats.z_score(value, pre_state) if has_history else 0.0
    threshold = _SENSITIVITY_THRESHOLDS.get(sensitivity, _SENSITIVITY_THRESHOLDS["medium"])
    deviation_detected = has_history and z >= threshold

    new_state = stats.update(pre_state, value)
    new_baseline = AgentBaselineRecord(
        agent_ref=agent_ref, action_type=action_type, mean=new_state.mean, m2=new_state.m2,
        sample_count=new_state.count, last_updated_at=now(),
    )
    return BaselineCheckResult(baseline=new_baseline, deviation_detected=deviation_detected, z_score=z)
