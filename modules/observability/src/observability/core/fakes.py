"""In-memory fakes for unit tests."""
from __future__ import annotations

from observability.core.domain import SpanRecord


class InMemoryObservabilityRepository:
    def __init__(self) -> None:
        self.spans: list[SpanRecord] = []

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
