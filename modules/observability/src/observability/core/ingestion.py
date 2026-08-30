"""OTLP Ingestion Endpoint (LLD §2 sub-components).

**Deviation from the LLD.** The LLD specifies OTLP/gRPC ingestion via a
real OpenTelemetry Collector, backed by Grafana Tempo/Mimir/Loki/Grafana.
Those are real infrastructure components (Go binaries, Helm charts) —
not something a single lightweight, independently-testable Python
microservice can stand up as part of its own unit-test tier, unlike this
platform's other named dependencies which are at least pip-installable.
This module instead accepts trace data via a simplified JSON HTTP
ingestion endpoint (`POST /v1/observability/ingest`) and stores spans in
its own Postgres table. The platform-specific layers this module actually
differentiates on — the Reasoning-Trace Reconstructor and Cost
Attribution Joiner — are genuinely implemented and tested against this
local store, matching the LLD's own testability contract almost verbatim
("tested with fixture trace data, independent of a live OTel pipeline").
Every other module's own OTel tracing setup (`telemetry/tracing.py`)
still exports real OTLP spans; wiring that OTLP endpoint at a real
Collector/Tempo stack instead of this module is a deployment-time
configuration decision, not a code change.
"""
from __future__ import annotations

from typing import Any

from observability.core.domain import SpanRecord, now
from observability.core.ports import ObservabilityRepository
from observability.telemetry.logging import get_logger

logger = get_logger(component="ingestion")


class IngestionService:
    def __init__(self, repository: ObservabilityRepository) -> None:
        self._repository = repository

    async def ingest(self, tenant_id: str, trace_id: str, spans: list[dict[str, Any]], workflow_type: str | None) -> int:
        count = 0
        for span_id, s in enumerate(spans, start=1):
            record = SpanRecord(
                id=f"{trace_id}:{s.get('span_id', span_id)}", tenant_id=tenant_id, trace_id=trace_id,
                span_id=str(s.get("span_id", span_id)), parent_span_id=s.get("parent_span_id"),
                name=s["name"], service_name=s.get("service_name", "unknown"), start_time=s["start_time"],
                end_time=s["end_time"], attributes=s.get("attributes", {}), status=s.get("status", "ok"),
                workflow_type=workflow_type,
            )
            await self._repository.create_span(record)
            count += 1
        logger.info("spans_ingested", trace_id=trace_id, count=count, at=now().isoformat())
        return count
