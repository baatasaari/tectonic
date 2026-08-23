"""Abstract ports this module depends on: persistence and LLM Gateway
(reasoning-trace narrative reconstruction)."""
from __future__ import annotations

from typing import Protocol

from observability.core.domain import SpanRecord


class ObservabilityRepository(Protocol):
    async def create_span(self, record: SpanRecord) -> SpanRecord: ...

    async def list_spans_for_trace(self, tenant_id: str, trace_id: str) -> list[SpanRecord]: ...

    async def list_traces_for_tenant(
        self, tenant_id: str, *, workflow_type: str | None = None,
    ) -> list[tuple[str, str | None]]:
        """Returns distinct (trace_id, workflow_type) pairs recorded for a tenant."""
        ...


class LLMGatewayClient(Protocol):
    async def narrate(self, trace_summary: list[dict]) -> str:
        """Produces a plain-language decision narrative from a structured trace
        summary (span names, durations, key attributes, in call order)."""
        ...
