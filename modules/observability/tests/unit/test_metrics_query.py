"""Tests for core/metrics_query.py -- the shared, real error-rate/p95
computation SLOService and AlertingService both evaluate from."""
from __future__ import annotations

from datetime import timedelta

from observability.core.domain import SLOMetric, SpanRecord, now
from observability.core.metrics_query import compute_metric


def _span(status: str = "ok", duration: float = 1.0) -> SpanRecord:
    base = now()
    return SpanRecord(
        id="x", tenant_id="acme", trace_id="t", span_id="s", parent_span_id=None, name="n",
        service_name="workflow-engine", start_time=base, end_time=base + timedelta(seconds=duration),
        status=status,
    )


def test_compute_metric_with_no_spans_returns_none_and_zero():
    value, count = compute_metric([], SLOMetric.ERROR_RATE)
    assert value is None
    assert count == 0


def test_error_rate_is_the_real_fraction_of_non_ok_spans():
    spans = [_span(status="ok"), _span(status="ok"), _span(status="error"), _span(status="ok")]

    value, count = compute_metric(spans, SLOMetric.ERROR_RATE)

    assert value == 0.25
    assert count == 4


def test_error_rate_with_all_ok_spans_is_zero():
    spans = [_span(status="ok") for _ in range(5)]

    value, _count = compute_metric(spans, SLOMetric.ERROR_RATE)

    assert value == 0.0


def test_latency_p95_of_a_single_span_is_its_own_duration():
    spans = [_span(duration=2.5)]

    value, count = compute_metric(spans, SLOMetric.LATENCY_P95)

    assert value == 2.5
    assert count == 1


def test_latency_p95_matches_the_standard_linear_interpolation_method():
    # 100 spans with durations 1..100 -- the standard (NumPy-default) linear
    # interpolation p95 of this exact set is 95.05.
    spans = [_span(duration=float(d)) for d in range(1, 101)]

    value, count = compute_metric(spans, SLOMetric.LATENCY_P95)

    assert count == 100
    assert value == 95.05


def test_latency_p95_is_dominated_by_the_slow_tail():
    spans = [_span(duration=1.0) for _ in range(99)] + [_span(duration=1000.0)]

    value, _count = compute_metric(spans, SLOMetric.LATENCY_P95)

    # 95th percentile of 99 fast spans + 1 very slow one still sits among the fast
    # ones -- proves this isn't accidentally computing a mean instead of a percentile.
    assert value == 1.0
