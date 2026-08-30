"""Cost Attribution Joiner (LLD §2 sub-components): combines cost data
(already present in trace attributes — LLM Gateway's `gen_ai.client.chat`
spans carry `gen_ai.usage.input_tokens`/`output_tokens` per the OTel GenAI
semantic convention plus its own `llm_gateway.cost` extension attribute,
per Module 3's `telemetry/tracing.py`) with performance data at query
time — no separate cost pipeline.
"""
from __future__ import annotations

from observability.core.domain import CostAttributionEntry, SpanRecord


class CostAttributionJoiner:
    def join(self, spans: list[SpanRecord]) -> list[CostAttributionEntry]:
        return [
            CostAttributionEntry(
                span_id=s.span_id, name=s.name, duration_seconds=s.duration_seconds,
                input_tokens=int(s.attributes.get("gen_ai.usage.input_tokens", 0) or 0),
                output_tokens=int(s.attributes.get("gen_ai.usage.output_tokens", 0) or 0),
                cost_usd=float(s.attributes.get("llm_gateway.cost", 0.0) or 0.0),
            )
            for s in sorted(spans, key=lambda s: s.start_time)
        ]

    @staticmethod
    def total_cost(entries: list[CostAttributionEntry]) -> float:
        return sum(e.cost_usd for e in entries)
