"""Alerting Service: the platform's real alert-rule engine over ingested
span data -- watch one `SLOMetric` over a trailing window, and reconcile
a firing/resolved event history from it. Reuses `core/metrics_query.py`,
the same computation `SLOService.evaluate` uses, so an SLO and an alert
rule watching the same metric over the same window always agree.

There's no real cron/scheduler infra in this sandbox to poll every
enabled rule on its own -- `evaluate_rule` is the real, tested
per-rule computation a real scheduler (or an operator, or a CI check)
is meant to call periodically; it's idempotent, so calling it more
often than the underlying data changes is harmless.
"""
from __future__ import annotations

from datetime import timedelta

from observability.core.domain import (
    AlertComparison,
    AlertEvent,
    AlertRule,
    AlertRuleNotFoundError,
    AlertStatus,
    SLOMetric,
    new_id,
    now,
)
from observability.core.metrics_query import compute_metric
from observability.core.ports import ObservabilityRepository
from observability.telemetry.metrics import observability_alert_events_total


class AlertingService:
    def __init__(self, repository: ObservabilityRepository) -> None:
        self._repository = repository

    async def create_rule(
        self, *, tenant_id: str, name: str, metric: SLOMetric, comparison: AlertComparison, threshold: float,
        window_hours: int, service_name: str | None = None,
    ) -> AlertRule:
        rule = AlertRule(
            id=new_id(), tenant_id=tenant_id, name=name, metric=metric, comparison=comparison, threshold=threshold,
            window_hours=window_hours, service_name=service_name,
        )
        return await self._repository.create_alert_rule(rule)

    async def get_rule(self, rule_id: str) -> AlertRule:
        rule = await self._repository.get_alert_rule(rule_id)
        if rule is None:
            raise AlertRuleNotFoundError(rule_id)
        return rule

    async def list_rules(
        self, *, tenant_id: str | None = None, enabled: bool | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AlertRule], int]:
        return await self._repository.list_alert_rules(tenant_id=tenant_id, enabled=enabled, limit=limit, offset=offset)

    async def set_enabled(self, rule_id: str, enabled: bool) -> AlertRule:
        rule = await self.get_rule(rule_id)
        rule.enabled = enabled
        return await self._repository.update_alert_rule(rule)

    async def evaluate_rule(self, rule_id: str) -> AlertEvent | None:
        """Returns the `AlertEvent` this evaluation produced or left
        standing, or `None` when the rule is disabled or its window has
        zero samples -- never fabricates a firing/resolved verdict from
        no data."""
        rule = await self.get_rule(rule_id)
        if not rule.enabled:
            return None

        since = now() - timedelta(hours=rule.window_hours)
        spans = await self._repository.list_spans_in_window(rule.tenant_id, service_name=rule.service_name, since=since)
        value, _count = compute_metric(spans, rule.metric)
        if value is None:
            return None

        breached = value > rule.threshold if rule.comparison == AlertComparison.GT else value < rule.threshold
        current = await self._repository.get_latest_alert_event(rule.id)

        if breached:
            if current is not None and current.status == AlertStatus.FIRING:
                return current  # still breached, already firing -- no duplicate event
            event = AlertEvent(
                id=new_id(), rule_id=rule.id, tenant_id=rule.tenant_id, status=AlertStatus.FIRING,
                value=value, threshold=rule.threshold,
            )
            created = await self._repository.create_alert_event(event)
            observability_alert_events_total.labels(tenant_id=rule.tenant_id, status="firing").inc()
            return created

        if current is not None and current.status == AlertStatus.FIRING:
            current.status = AlertStatus.RESOLVED
            current.resolved_at = now()
            resolved = await self._repository.update_alert_event(current)
            observability_alert_events_total.labels(tenant_id=rule.tenant_id, status="resolved").inc()
            return resolved

        return current  # not breached, and nothing was firing -- nothing to reconcile
