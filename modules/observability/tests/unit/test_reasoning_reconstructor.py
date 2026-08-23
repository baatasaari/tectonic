from datetime import UTC, datetime, timedelta

from observability.core.domain import SpanRecord
from observability.core.fakes import StubLLMGatewayClient


def _span(name, start_offset, duration=1.0):
    start = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=start_offset)
    return SpanRecord(
        id=name, tenant_id="t1", trace_id="trace-1", span_id=name, parent_span_id=None, name=name,
        service_name="workflow-engine", start_time=start, end_time=start + timedelta(seconds=duration),
    )


async def test_reconstruct_calls_llm_gateway_with_ordered_spans(harness):
    spans = [_span("respond", start_offset=2), _span("retrieve", start_offset=0), _span("classify", start_offset=1)]
    narrative = await harness.reconstructor.reconstruct(spans)

    assert narrative == harness.llm_gateway.narrative
    call = harness.llm_gateway.calls[0]
    assert [s["name"] for s in call] == ["retrieve", "classify", "respond"]


async def test_reconstruct_falls_back_on_llm_gateway_failure(harness_factory):
    h = harness_factory(llm_gateway=StubLLMGatewayClient(should_fail=True))
    spans = [_span("retrieve", 0), _span("respond", 1)]

    narrative = await h.reconstructor.reconstruct(spans)

    assert "retrieve" in narrative
    assert "respond" in narrative
    assert "->" in narrative


async def test_reconstruct_uses_fallback_when_disabled(harness_factory):
    h = harness_factory(narrative_enabled=False)
    spans = [_span("retrieve", 0)]

    narrative = await h.reconstructor.reconstruct(spans)

    assert h.llm_gateway.calls == []
    assert "retrieve" in narrative


async def test_reconstruct_empty_trace_says_so(harness):
    narrative = await harness.reconstructor.reconstruct([])
    assert "No spans" in narrative
