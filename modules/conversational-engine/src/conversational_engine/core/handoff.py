"""Handoff Trigger Engine (LLD §2.2): decides when to escalate to a human
or another agent — rule-based on emotion score, explicit request, or
repeated guardrail refusals. Deterministic by design, same rationale as
Module 1's symbolic step routing: a governance-relevant decision should be
traceable to a specific rule, not an opaque model judgement.
"""
from __future__ import annotations

from dataclasses import dataclass

from conversational_engine.config import HandoffConfig
from conversational_engine.core.domain import HandoffTriggerReason


@dataclass
class HandoffDecision:
    trigger: bool
    reason: HandoffTriggerReason | None = None


class HandoffTriggerEngine:
    def __init__(self, config: HandoffConfig) -> None:
        self.config = config

    def evaluate(
        self, *, emotion_score: float, explicit_request: bool, consecutive_refusals: int
    ) -> HandoffDecision:
        if explicit_request:
            return HandoffDecision(trigger=True, reason=HandoffTriggerReason.EXPLICIT)
        if emotion_score >= self.config.emotion_score_threshold:
            return HandoffDecision(trigger=True, reason=HandoffTriggerReason.EMOTION)
        if consecutive_refusals >= self.config.repeated_refusal_threshold:
            return HandoffDecision(trigger=True, reason=HandoffTriggerReason.REPEATED_REFUSAL)
        return HandoffDecision(trigger=False)
