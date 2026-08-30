"""Tests for core/alerting_service.py -- real threshold evaluation and
the firing/resolved event state machine it reconciles from it."""
from __future__ import annotations

import pytest

from observability.core.domain import (
    AlertComparison,
    AlertRuleNotFoundError,
    AlertStatus,
    SLOMetric,
)


async def test_evaluate_rule_creates_a_firing_event_when_breached(harness):
    rule = await harness.alerting_service.create_rule(
        tenant_id="acme", name="High error rate", metric=SLOMetric.ERROR_RATE, comparison=AlertComparison.GT,
        threshold=0.1, window_hours=1,
    )
    await harness.add_span("acme", "t1", "s1", "run", status="error")
    await harness.add_span("acme", "t1", "s2", "run", status="ok")

    event = await harness.alerting_service.evaluate_rule(rule.id)

    assert event is not None
    assert event.status == AlertStatus.FIRING
    assert event.value == 0.5


async def test_evaluate_rule_does_not_fire_when_not_breached(harness):
    rule = await harness.alerting_service.create_rule(
        tenant_id="acme", name="High error rate", metric=SLOMetric.ERROR_RATE, comparison=AlertComparison.GT,
        threshold=0.5, window_hours=1,
    )
    await harness.add_span("acme", "t1", "s1", "run", status="ok")

    event = await harness.alerting_service.evaluate_rule(rule.id)

    assert event is None


async def test_re_evaluating_while_still_breached_does_not_duplicate_the_event(harness):
    rule = await harness.alerting_service.create_rule(
        tenant_id="acme", name="High error rate", metric=SLOMetric.ERROR_RATE, comparison=AlertComparison.GT,
        threshold=0.1, window_hours=1,
    )
    await harness.add_span("acme", "t1", "s1", "run", status="error")

    first = await harness.alerting_service.evaluate_rule(rule.id)
    second = await harness.alerting_service.evaluate_rule(rule.id)

    assert first.id == second.id
    _events, total = await harness.repository.list_alert_events(tenant_id="acme")
    assert total == 1


async def test_evaluate_rule_resolves_a_firing_event_once_no_longer_breached(harness):
    rule = await harness.alerting_service.create_rule(
        tenant_id="acme", name="High error rate", metric=SLOMetric.ERROR_RATE, comparison=AlertComparison.GT,
        threshold=0.1, window_hours=1,
    )
    await harness.add_span("acme", "t1", "s1", "run", status="error")
    firing = await harness.alerting_service.evaluate_rule(rule.id)
    assert firing.status == AlertStatus.FIRING

    # Fresh, all-ok traffic replaces the error in this window's evaluation.
    harness.repository.spans.clear()
    await harness.add_span("acme", "t2", "s1", "run", status="ok")

    resolved = await harness.alerting_service.evaluate_rule(rule.id)

    assert resolved.id == firing.id
    assert resolved.status == AlertStatus.RESOLVED
    assert resolved.resolved_at is not None


async def test_evaluate_rule_lt_comparison(harness):
    rule = await harness.alerting_service.create_rule(
        tenant_id="acme", name="Traffic dropped", metric=SLOMetric.ERROR_RATE, comparison=AlertComparison.LT,
        threshold=0.5, window_hours=1,
    )
    await harness.add_span("acme", "t1", "s1", "run", status="ok")

    event = await harness.alerting_service.evaluate_rule(rule.id)

    assert event is not None
    assert event.status == AlertStatus.FIRING  # 0.0 < 0.5 -- breached


async def test_evaluate_rule_with_no_data_returns_none_not_a_fabricated_verdict(harness):
    rule = await harness.alerting_service.create_rule(
        tenant_id="acme", name="No traffic yet", metric=SLOMetric.ERROR_RATE, comparison=AlertComparison.GT,
        threshold=0.1, window_hours=1,
    )

    event = await harness.alerting_service.evaluate_rule(rule.id)

    assert event is None


async def test_disabled_rule_is_never_evaluated(harness):
    rule = await harness.alerting_service.create_rule(
        tenant_id="acme", name="High error rate", metric=SLOMetric.ERROR_RATE, comparison=AlertComparison.GT,
        threshold=0.1, window_hours=1,
    )
    await harness.add_span("acme", "t1", "s1", "run", status="error")
    await harness.alerting_service.set_enabled(rule.id, False)

    event = await harness.alerting_service.evaluate_rule(rule.id)

    assert event is None


async def test_evaluate_raises_for_a_missing_rule(harness):
    with pytest.raises(AlertRuleNotFoundError):
        await harness.alerting_service.evaluate_rule("does-not-exist")


async def test_list_rules_filters_by_enabled(harness):
    a = await harness.alerting_service.create_rule(
        tenant_id="acme", name="a", metric=SLOMetric.ERROR_RATE, comparison=AlertComparison.GT, threshold=0.1,
        window_hours=1,
    )
    await harness.alerting_service.create_rule(
        tenant_id="acme", name="b", metric=SLOMetric.ERROR_RATE, comparison=AlertComparison.GT, threshold=0.1,
        window_hours=1,
    )
    await harness.alerting_service.set_enabled(a.id, False)

    enabled, total = await harness.alerting_service.list_rules(tenant_id="acme", enabled=True)

    assert total == 1
    assert enabled[0].name == "b"
