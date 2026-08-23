"""Emotion/Urgency Detector (LLD §2.2, differentiator: "emotional and
urgency-aware routing"). The LLD calls for "a lightweight classifier
(fine-tuned small model or LLM-based classification call via LLM Gateway),
not a separate heavyweight service." This implements the lightweight-
heuristic half of that directly (no added latency, no extra dependency),
with an optional LLM Gateway classification call for cases the heuristic is
unsure about — mirroring Module 1's "use the LLD's own stated fallback"
pattern for the symbolic rule engine.
"""
from __future__ import annotations

import re

from conversational_engine.core.ports import LLMGatewayClient

_FRUSTRATION_MARKERS = (
    "angry",
    "furious",
    "unacceptable",
    "ridiculous",
    "worst",
    "terrible",
    "useless",
    "scam",
    "refund",
    "cancel my",
    "speak to a human",
    "speak to someone",
    "this is a joke",
    "fed up",
)
_URGENCY_MARKERS = ("urgent", "immediately", "asap", "right now", "emergency", "critical")

# Heuristic confidence band: outside [LOW, HIGH] the signal is treated as
# strong enough on its own; inside it, an LLM classification call (if a
# client is configured) refines the score rather than guessing.
_UNCERTAIN_BAND = (0.35, 0.65)


def _heuristic_score(text: str) -> float:
    lowered = text.lower()
    score = 0.0

    marker_hits = sum(1 for m in _FRUSTRATION_MARKERS if m in lowered)
    score += min(marker_hits * 0.25, 0.75)

    urgency_hits = sum(1 for m in _URGENCY_MARKERS if m in lowered)
    score += min(urgency_hits * 0.15, 0.3)

    exclamations = text.count("!")
    score += min(exclamations * 0.1, 0.2)

    letters = [c for c in text if c.isalpha()]
    if letters:
        caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if caps_ratio > 0.5 and len(letters) > 6:
            score += 0.2

    repeated_punct = bool(re.search(r"[!?]{2,}", text))
    if repeated_punct:
        score += 0.1

    return max(0.0, min(1.0, score))


class EmotionUrgencyDetector:
    def __init__(self, llm_gateway: LLMGatewayClient | None = None) -> None:
        self.llm_gateway = llm_gateway

    async def score(self, text: str, tenant_id: str) -> float:
        heuristic = _heuristic_score(text)
        low, high = _UNCERTAIN_BAND
        if self.llm_gateway is None or not (low <= heuristic <= high):
            return heuristic

        try:
            classification = await self.llm_gateway.classify(
                text=text, taxonomy=["calm", "frustrated", "urgent"], tenant_id=tenant_id
            )
        except Exception:  # classification is a refinement, never a hard dependency
            return heuristic

        llm_score = classification.get("frustrated", 0.0) + classification.get("urgent", 0.0)
        return max(0.0, min(1.0, (heuristic + llm_score) / 2))
