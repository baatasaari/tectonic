"""Reasoning-Trace Reconstructor (LLD §2 sub-components, §Level 3
"Sequence: reasoning-trace narrative generation on demand"): turns a raw
trace tree into a plain-language decision narrative via an LLM Gateway
call.

A deterministic, span-name-and-attribute-based narrative is used as the
fallback when the LLM Gateway call fails or the feature is disabled — the
same "LLM call for the good case, a documented lesser fallback for the
degraded case" pattern used elsewhere in this platform (e.g. Guardrails'
ambiguous-jailbreak fallback), rather than surfacing an error to a support
engineer mid-incident.
"""
from __future__ import annotations

from observability.core.domain import SpanRecord
from observability.core.ports import LLMGatewayClient
from observability.telemetry.logging import get_logger

logger = get_logger(component="reasoning_reconstructor")


class ReasoningTraceReconstructor:
    def __init__(self, llm_gateway: LLMGatewayClient, *, enabled: bool = True) -> None:
        self._llm_gateway = llm_gateway
        self._enabled = enabled

    async def reconstruct(self, spans: list[SpanRecord]) -> str:
        ordered = sorted(spans, key=lambda s: s.start_time)
        if not ordered or not self._enabled:
            return self._fallback_narrative(ordered)

        summary = [
            {
                "name": s.name, "service": s.service_name, "duration_seconds": round(s.duration_seconds, 3),
                "status": s.status, "attributes": s.attributes,
            }
            for s in ordered
        ]
        try:
            return await self._llm_gateway.narrate(summary)
        except Exception as exc:
            logger.warning("reasoning_narrative_llm_call_failed", error=str(exc))
            return self._fallback_narrative(ordered)

    @staticmethod
    def _fallback_narrative(spans: list[SpanRecord]) -> str:
        if not spans:
            return "No spans recorded for this trace."
        steps = [f"{s.name} ({s.service_name}, {s.duration_seconds:.3f}s, {s.status})" for s in spans]
        return "Trace steps in order: " + " -> ".join(steps)
