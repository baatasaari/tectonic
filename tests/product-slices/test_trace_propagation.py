"""Ticket #82, Definition of Done item 5 (scoped down after review -- see
docs/phase2-product-slice-01-support-agent.md and this directory's own
README): every module in this platform already calls
`HTTPXClientInstrumentor().instrument()` alongside
`FastAPIInstrumentor.instrument_app(app)` (Observability's own README
documents this as a platform-wide fix, verified at the time via "an
isolated reproduction ... shows the caller span, the httpx client span,
and the downstream server span all carrying the identical trace_id").
That verification was never committed as an automated test anywhere in
this repo -- this file is that missing permanent regression test, not a
new mechanism. It deliberately does NOT stand up this slice's own real
15-module stack (that's test_support_agent.py's job) or attempt to land
spans in Observability's own real store (no real OTel Collector/Tempo is
available in this sandbox -- see CLAUDE.md's "Sandbox infrastructure").
It reproduces the exact isolated pair the README already describes: two
tiny FastAPI apps, instrumented the identical way every real module's own
main.py instruments itself, chained through a real (if in-process, ASGI-
transport) HTTP call, with an InMemorySpanExporter capturing every span
this process's global TracerProvider sees.
"""
from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

pytestmark = pytest.mark.asyncio


@pytest.fixture
def exporter():
    """A fresh TracerProvider + InMemorySpanExporter installed as the
    process-global tracer for the duration of one test -- OTel's own
    `set_tracer_provider` is a one-shot global, so every test using this
    fixture gets its own isolated provider rather than fighting over a
    module-level singleton another test already set."""
    provider = TracerProvider()
    mem_exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(mem_exporter))
    trace.set_tracer_provider(provider)
    yield mem_exporter
    mem_exporter.clear()


async def test_traceparent_propagates_real_trace_id_across_a_real_http_hop(exporter):
    """Downstream app (stands in for e.g. Workflow Engine): a real FastAPI
    app, instrumented exactly the way every module's own main.py
    instruments itself (`FastAPIInstrumentor.instrument_app`), whose own
    handler makes no further calls -- this is the leaf of the chain."""
    downstream = FastAPI()

    @downstream.get("/v1/downstream/ping")
    async def ping(request: Request) -> dict:
        span = trace.get_current_span()
        return {"trace_id": format(span.get_span_context().trace_id, "032x")}

    FastAPIInstrumentor.instrument_app(downstream)

    # Upstream side (stands in for e.g. Conversational Engine calling
    # Workflow Engine): a real httpx.AsyncClient, instrumented exactly the
    # way every module's own main.py instruments its outbound client
    # (`HTTPXClientInstrumentor().instrument()`), talking to the
    # downstream app over a real ASGI transport (an in-process substitute
    # for a real TCP hop -- the instrumentation and header-propagation
    # logic under test doesn't know or care that this isn't a real socket).
    HTTPXClientInstrumentor().instrument()
    try:
        tracer = trace.get_tracer("upstream-caller")
        transport = httpx.ASGITransport(app=downstream)
        async with httpx.AsyncClient(transport=transport, base_url="http://downstream.local") as client:
            with tracer.start_as_current_span("upstream-caller-span") as caller_span:
                caller_trace_id = format(caller_span.get_span_context().trace_id, "032x")
                resp = await client.get("/v1/downstream/ping")
    finally:
        HTTPXClientInstrumentor().uninstrument()

    assert resp.status_code == 200
    downstream_reported_trace_id = resp.json()["trace_id"]

    spans = exporter.get_finished_spans()
    spans_by_name = {s.name: s for s in spans}
    assert "upstream-caller-span" in spans_by_name
    # FastAPIInstrumentor names its server span after the matched route;
    # HTTPXClientInstrumentor's own client-side spans are named after the
    # ASGI-transport-internal send/receive events for the ASGI transport
    # specifically (a real TCP transport names its client span "GET"
    # instead) -- this test asserts on trace_id continuity across every
    # span OTel actually recorded, not on one exact client-span name, since
    # that name is a transport-specific implementation detail, not the
    # thing ticket #82 needs proven.
    assert "GET /v1/downstream/ping" in spans_by_name
    assert len(spans) >= 3, f"expected caller + httpx client + server spans, got: {list(spans_by_name)}"

    server_span = spans_by_name["GET /v1/downstream/ping"]
    server_span_trace_id = format(server_span.context.trace_id, "032x")

    all_trace_ids = {format(s.context.trace_id, "032x") for s in spans}

    # The actual claim under test: one real trace_id, not several unrelated
    # ones -- every span OTel recorded for this one request (the caller's
    # own span, the httpx client's internal spans, the downstream FastAPI
    # server span), plus the trace_id the downstream handler itself
    # observed via `trace.get_current_span()`, are all the identical
    # value. This is what "distributed" means for a trace; disconnected
    # trace_ids here would mean the propagation this platform depends on
    # is broken.
    assert all_trace_ids == {caller_trace_id}, f"expected one shared trace_id, got: {all_trace_ids}"
    assert server_span_trace_id == caller_trace_id
    assert downstream_reported_trace_id == caller_trace_id


async def test_two_independent_requests_get_two_different_trace_ids(exporter):
    """Guards against a trivially-passing-but-wrong implementation of the
    test above (e.g. a global default trace_id, or a fixture leaking state
    across tests) -- two genuinely separate requests must produce two
    genuinely separate trace_ids, not the same one twice."""
    downstream = FastAPI()

    @downstream.get("/v1/downstream/ping")
    async def ping() -> dict:
        span = trace.get_current_span()
        return {"trace_id": format(span.get_span_context().trace_id, "032x")}

    FastAPIInstrumentor.instrument_app(downstream)

    HTTPXClientInstrumentor().instrument()
    try:
        transport = httpx.ASGITransport(app=downstream)
        async with httpx.AsyncClient(transport=transport, base_url="http://downstream.local") as client:
            first = (await client.get("/v1/downstream/ping")).json()["trace_id"]
            second = (await client.get("/v1/downstream/ping")).json()["trace_id"]
    finally:
        HTTPXClientInstrumentor().uninstrument()

    assert first != second
