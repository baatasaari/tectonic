"""Abstract ports this module depends on: persistence and LLM Gateway
(reasoning-trace narrative reconstruction)."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from observability.core.domain import (
    AlertEvent,
    AlertRule,
    AlertStatus,
    SLODefinition,
    SpanRecord,
    TraceSummary,
)


class ObservabilityRepository(Protocol):
    async def create_span(self, record: SpanRecord) -> SpanRecord: ...

    async def list_spans_for_trace(self, tenant_id: str, trace_id: str) -> list[SpanRecord]: ...

    async def list_traces_for_tenant(
        self, tenant_id: str, *, workflow_type: str | None = None,
    ) -> list[tuple[str, str | None]]:
        """Returns distinct (trace_id, workflow_type) pairs recorded for a tenant."""
        ...

    async def list_trace_summaries(
        self, tenant_id: str, *, workflow_type: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[TraceSummary], int]:
        """The trace *query* surface's own list endpoint -- one row per
        trace, aggregated by a real query (span count, time range,
        whether any span errored), never every span pulled client-side
        just to summarize it."""
        ...

    async def list_spans_in_window(
        self, tenant_id: str, *, service_name: str | None, since: datetime,
    ) -> list[SpanRecord]:
        """Every span for this tenant (optionally scoped to one
        `service_name`) with `start_time >= since` -- what
        `SLOService`/`AlertingService` evaluate a metric over."""
        ...

    # -- SLOs --

    async def create_slo(self, record: SLODefinition) -> SLODefinition: ...

    async def get_slo(self, slo_id: str) -> SLODefinition | None: ...

    async def list_slos(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[SLODefinition], int]: ...

    # -- Alert rules --

    async def create_alert_rule(self, record: AlertRule) -> AlertRule: ...

    async def get_alert_rule(self, rule_id: str) -> AlertRule | None: ...

    async def update_alert_rule(self, record: AlertRule) -> AlertRule: ...

    async def list_alert_rules(
        self, *, tenant_id: str | None = None, enabled: bool | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AlertRule], int]: ...

    # -- Alert events --

    async def create_alert_event(self, record: AlertEvent) -> AlertEvent: ...

    async def update_alert_event(self, record: AlertEvent) -> AlertEvent: ...

    async def get_latest_alert_event(self, rule_id: str) -> AlertEvent | None:
        """The most recent event for this rule, whatever its status --
        `AlertingService.evaluate_rule`'s own idempotency check: firing
        again while already firing must never create a second event,
        and resolving needs to know which event to resolve."""
        ...

    async def list_alert_events(
        self, *, tenant_id: str | None = None, status: AlertStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AlertEvent], int]: ...


class LLMGatewayClient(Protocol):
    async def narrate(self, trace_summary: list[dict]) -> str:
        """Produces a plain-language decision narrative from a structured trace
        summary (span names, durations, key attributes, in call order)."""
        ...
