from datetime import UTC, datetime, timedelta

import pytest

from observability.core.cost_attribution import CostAttributionJoiner
from observability.core.domain import SpanRecord


def _span(name, start_offset, duration, **attrs):
    start = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=start_offset)
    return SpanRecord(
        id=name, tenant_id="t1", trace_id="trace-1", span_id=name, parent_span_id=None, name=name,
        service_name="llm-gateway", start_time=start, end_time=start + timedelta(seconds=duration), attributes=attrs,
    )


def test_join_reads_real_llm_gateway_span_attributes():
    joiner = CostAttributionJoiner()
    spans = [
        _span(
            "gen_ai.client.chat", 0, 1.5,
            **{"gen_ai.usage.input_tokens": 120, "gen_ai.usage.output_tokens": 45, "llm_gateway.cost": 0.0021},
        )
    ]

    entries = joiner.join(spans)

    assert len(entries) == 1
    assert entries[0].input_tokens == 120
    assert entries[0].output_tokens == 45
    assert entries[0].cost_usd == 0.0021
    assert entries[0].duration_seconds == 1.5


def test_join_defaults_missing_cost_attributes_to_zero():
    joiner = CostAttributionJoiner()
    spans = [_span("some.other.span", 0, 1.0)]

    entries = joiner.join(spans)

    assert entries[0].input_tokens == 0
    assert entries[0].output_tokens == 0
    assert entries[0].cost_usd == 0.0


def test_join_orders_entries_by_start_time():
    joiner = CostAttributionJoiner()
    spans = [_span("second", 5, 1.0), _span("first", 0, 1.0)]

    entries = joiner.join(spans)

    assert [e.name for e in entries] == ["first", "second"]


def test_total_cost_sums_all_entries():
    joiner = CostAttributionJoiner()
    spans = [
        _span("a", 0, 1.0, **{"llm_gateway.cost": 0.01}),
        _span("b", 1, 1.0, **{"llm_gateway.cost": 0.02}),
    ]
    entries = joiner.join(spans)
    assert joiner.total_cost(entries) == pytest.approx(0.03)
