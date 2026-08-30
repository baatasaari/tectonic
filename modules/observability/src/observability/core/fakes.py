"""In-memory fakes for unit tests."""
from __future__ import annotations

from datetime import datetime

from observability.core.domain import (
    AlertEvent,
    AlertRule,
    AlertStatus,
    SLODefinition,
    SpanRecord,
    TraceSummary,
)


class InMemoryObservabilityRepository:
    def __init__(self) -> None:
        self.spans: list[SpanRecord] = []
        self.slos: dict[str, SLODefinition] = {}
        self.alert_rules: dict[str, AlertRule] = {}
        self.alert_events: list[AlertEvent] = []

    async def create_span(self, record: SpanRecord) -> SpanRecord:
        self.spans.append(record)
        return record

    async def list_spans_for_trace(self, tenant_id: str, trace_id: str) -> list[SpanRecord]:
        return [s for s in self.spans if s.tenant_id == tenant_id and s.trace_id == trace_id]

    async def list_traces_for_tenant(
        self, tenant_id: str, *, workflow_type: str | None = None,
    ) -> list[tuple[str, str | None]]:
        seen: dict[str, str | None] = {}
        for s in self.spans:
            if s.tenant_id != tenant_id:
                continue
            if workflow_type is not None and s.workflow_type != workflow_type:
                continue
            seen.setdefault(s.trace_id, s.workflow_type)
        return list(seen.items())

    async def list_trace_summaries(
        self, tenant_id: str, *, workflow_type: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[TraceSummary], int]:
        by_trace: dict[str, list[SpanRecord]] = {}
        for s in self.spans:
            if s.tenant_id != tenant_id:
                continue
            if workflow_type is not None and s.workflow_type != workflow_type:
                continue
            by_trace.setdefault(s.trace_id, []).append(s)

        summaries = [
            TraceSummary(
                trace_id=trace_id, tenant_id=tenant_id, workflow_type=spans[0].workflow_type, span_count=len(spans),
                start_time=min(s.start_time for s in spans), end_time=max(s.end_time for s in spans),
                has_error=any(s.status != "ok" for s in spans),
            )
            for trace_id, spans in by_trace.items()
        ]
        summaries.sort(key=lambda t: t.start_time, reverse=True)
        return summaries[offset:offset + limit], len(summaries)

    async def list_spans_in_window(
        self, tenant_id: str, *, service_name: str | None, since: datetime,
    ) -> list[SpanRecord]:
        return [
            s for s in self.spans
            if s.tenant_id == tenant_id and s.start_time >= since
            and (service_name is None or s.service_name == service_name)
        ]

    async def create_slo(self, record: SLODefinition) -> SLODefinition:
        self.slos[record.id] = record
        return record

    async def get_slo(self, slo_id: str) -> SLODefinition | None:
        return self.slos.get(slo_id)

    async def list_slos(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[SLODefinition], int]:
        results = list(self.slos.values())
        if tenant_id is not None:
            results = [s for s in results if s.tenant_id == tenant_id]
        results = sorted(results, key=lambda s: s.created_at)
        return results[offset:offset + limit], len(results)

    async def create_alert_rule(self, record: AlertRule) -> AlertRule:
        self.alert_rules[record.id] = record
        return record

    async def get_alert_rule(self, rule_id: str) -> AlertRule | None:
        return self.alert_rules.get(rule_id)

    async def update_alert_rule(self, record: AlertRule) -> AlertRule:
        self.alert_rules[record.id] = record
        return record

    async def list_alert_rules(
        self, *, tenant_id: str | None = None, enabled: bool | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AlertRule], int]:
        results = list(self.alert_rules.values())
        if tenant_id is not None:
            results = [r for r in results if r.tenant_id == tenant_id]
        if enabled is not None:
            results = [r for r in results if r.enabled == enabled]
        results = sorted(results, key=lambda r: r.created_at)
        return results[offset:offset + limit], len(results)

    async def create_alert_event(self, record: AlertEvent) -> AlertEvent:
        self.alert_events.append(record)
        return record

    async def update_alert_event(self, record: AlertEvent) -> AlertEvent:
        for i, existing in enumerate(self.alert_events):
            if existing.id == record.id:
                self.alert_events[i] = record
                return record
        self.alert_events.append(record)
        return record

    async def get_latest_alert_event(self, rule_id: str) -> AlertEvent | None:
        candidates = [e for e in self.alert_events if e.rule_id == rule_id]
        return max(candidates, key=lambda e: e.triggered_at) if candidates else None

    async def list_alert_events(
        self, *, tenant_id: str | None = None, status: AlertStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AlertEvent], int]:
        results = list(self.alert_events)
        if tenant_id is not None:
            results = [e for e in results if e.tenant_id == tenant_id]
        if status is not None:
            results = [e for e in results if e.status == status]
        results = sorted(results, key=lambda e: e.triggered_at, reverse=True)
        return results[offset:offset + limit], len(results)


class StubLLMGatewayClient:
    def __init__(self, narrative: str = "The agent completed the workflow successfully.", should_fail: bool = False) -> None:
        self.calls: list[list[dict]] = []
        self.narrative = narrative
        self.should_fail = should_fail

    async def narrate(self, trace_summary: list[dict]) -> str:
        self.calls.append(trace_summary)
        if self.should_fail:
            raise RuntimeError("LLM Gateway unavailable")
        return self.narrative
