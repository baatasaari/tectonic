"""Tests for the trace query surface's own aggregation --
`ObservabilityRepository.list_trace_summaries` -- against the in-memory
fake (see tests/integration for the real Postgres GROUP BY)."""
from __future__ import annotations

from datetime import timedelta

from observability.core.domain import now


async def test_list_trace_summaries_aggregates_span_count_and_time_range(harness):
    start = now()
    await harness.add_span(
        "acme", "t1", "s1", "step-1", start_time=start, end_time=start + timedelta(seconds=1),
        workflow_type="onboarding",
    )
    await harness.add_span(
        "acme", "t1", "s2", "step-2", start_time=start + timedelta(seconds=1), end_time=start + timedelta(seconds=3),
        workflow_type="onboarding",
    )

    summaries, total = await harness.repository.list_trace_summaries("acme")

    assert total == 1
    summary = summaries[0]
    assert summary.trace_id == "t1"
    assert summary.span_count == 2
    assert summary.start_time == start
    assert summary.end_time == start + timedelta(seconds=3)
    assert summary.duration_seconds == 3.0
    assert summary.has_error is False


async def test_list_trace_summaries_flags_has_error_when_any_span_errored(harness):
    await harness.add_span("acme", "t1", "s1", "step-1", status="ok")
    await harness.add_span("acme", "t1", "s2", "step-2", status="error")

    summaries, _total = await harness.repository.list_trace_summaries("acme")

    assert summaries[0].has_error is True


async def test_list_trace_summaries_filters_by_workflow_type(harness):
    await harness.add_span("acme", "t1", "s1", "step", workflow_type="onboarding")
    await harness.add_span("acme", "t2", "s1", "step", workflow_type="checkout")

    summaries, total = await harness.repository.list_trace_summaries("acme", workflow_type="checkout")

    assert total == 1
    assert summaries[0].trace_id == "t2"


async def test_list_trace_summaries_scopes_to_tenant(harness):
    await harness.add_span("acme", "t1", "s1", "step")
    await harness.add_span("other-tenant", "t2", "s1", "step")

    summaries, total = await harness.repository.list_trace_summaries("acme")

    assert total == 1
    assert summaries[0].tenant_id == "acme"


async def test_list_trace_summaries_orders_newest_first(harness):
    older = now() - timedelta(hours=1)
    newer = now()
    await harness.add_span("acme", "old-trace", "s1", "step", start_time=older, end_time=older)
    await harness.add_span("acme", "new-trace", "s1", "step", start_time=newer, end_time=newer)

    summaries, _total = await harness.repository.list_trace_summaries("acme")

    assert [s.trace_id for s in summaries] == ["new-trace", "old-trace"]


async def test_list_trace_summaries_paginates(harness):
    for i in range(5):
        t = now() - timedelta(minutes=i)
        await harness.add_span("acme", f"t{i}", "s1", "step", start_time=t, end_time=t)

    page, total = await harness.repository.list_trace_summaries("acme", limit=2, offset=0)

    assert total == 5
    assert len(page) == 2
