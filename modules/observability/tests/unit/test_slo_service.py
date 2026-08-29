"""Tests for core/slo_service.py -- real evaluation against ingested
span data, insufficient-data-over-fabrication with zero samples."""
from __future__ import annotations

from datetime import timedelta

import pytest

from observability.core.domain import SLOMetric, SLONotFoundError, now


async def test_evaluate_error_rate_slo_computes_the_real_fraction(harness):
    slo = await harness.slo_service.create(
        tenant_id="acme", name="Workflow error rate", metric=SLOMetric.ERROR_RATE, target=0.1, window_hours=24,
        service_name="workflow-engine",
    )
    await harness.add_span("acme", "t1", "s1", "run", status="ok")
    await harness.add_span("acme", "t1", "s2", "run", status="ok")
    await harness.add_span("acme", "t1", "s3", "run", status="error")

    result = await harness.slo_service.evaluate(slo.id)

    assert result.sample_count == 3
    assert result.current_value == pytest.approx(1 / 3)
    assert result.compliant is False  # 0.333 > 0.1 target
    assert result.error_budget_remaining < 0  # over budget


async def test_evaluate_error_rate_slo_within_target_is_compliant_with_positive_budget(harness):
    slo = await harness.slo_service.create(
        tenant_id="acme", name="Workflow error rate", metric=SLOMetric.ERROR_RATE, target=0.5, window_hours=24,
    )
    await harness.add_span("acme", "t1", "s1", "run", status="ok")
    await harness.add_span("acme", "t1", "s2", "run", status="error")

    result = await harness.slo_service.evaluate(slo.id)

    assert result.current_value == 0.5
    assert result.compliant is True
    assert result.error_budget_remaining == pytest.approx(0.0)


async def test_evaluate_latency_slo_never_reports_an_error_budget(harness):
    slo = await harness.slo_service.create(
        tenant_id="acme", name="p95 latency", metric=SLOMetric.LATENCY_P95, target=2.0, window_hours=24,
    )
    end = now()
    await harness.add_span("acme", "t1", "s1", "run", start_time=end, end_time=end + timedelta(seconds=1))

    result = await harness.slo_service.evaluate(slo.id)

    assert result.compliant is True
    assert result.error_budget_remaining is None


async def test_evaluate_with_zero_samples_reports_none_not_a_fabricated_pass(harness):
    slo = await harness.slo_service.create(
        tenant_id="acme", name="No traffic yet", metric=SLOMetric.ERROR_RATE, target=0.1, window_hours=24,
    )

    result = await harness.slo_service.evaluate(slo.id)

    assert result.sample_count == 0
    assert result.current_value is None
    assert result.compliant is None
    assert result.error_budget_remaining is None


async def test_evaluate_only_counts_spans_inside_the_window(harness):
    slo = await harness.slo_service.create(
        tenant_id="acme", name="1h error rate", metric=SLOMetric.ERROR_RATE, target=0.5, window_hours=1,
    )
    stale = now() - timedelta(hours=2)
    await harness.add_span("acme", "t1", "s1", "run", status="error", start_time=stale, end_time=stale)
    await harness.add_span("acme", "t2", "s1", "run", status="ok")

    result = await harness.slo_service.evaluate(slo.id)

    assert result.sample_count == 1  # the 2-hour-old error span is outside the 1h window
    assert result.current_value == 0.0


async def test_evaluate_scoped_to_one_service_ignores_other_services(harness):
    slo = await harness.slo_service.create(
        tenant_id="acme", name="LLM Gateway errors", metric=SLOMetric.ERROR_RATE, target=0.1, window_hours=24,
        service_name="llm-gateway",
    )
    await harness.add_span("acme", "t1", "s1", "run", service_name="llm-gateway", status="ok")
    await harness.add_span("acme", "t2", "s1", "run", service_name="workflow-engine", status="error")

    result = await harness.slo_service.evaluate(slo.id)

    assert result.sample_count == 1
    assert result.current_value == 0.0


async def test_evaluate_raises_for_a_missing_slo(harness):
    with pytest.raises(SLONotFoundError):
        await harness.slo_service.evaluate("does-not-exist")


async def test_list_slos_filters_by_tenant(harness):
    await harness.slo_service.create(
        tenant_id="acme", name="a", metric=SLOMetric.ERROR_RATE, target=0.1, window_hours=24,
    )
    await harness.slo_service.create(
        tenant_id="other", name="b", metric=SLOMetric.ERROR_RATE, target=0.1, window_hours=24,
    )

    results, total = await harness.slo_service.list(tenant_id="acme")

    assert total == 1
    assert results[0].tenant_id == "acme"
