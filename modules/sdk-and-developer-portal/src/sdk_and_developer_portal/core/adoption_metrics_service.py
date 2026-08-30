"""Adoption Metrics Service (LLD §2 sub-components, §Level 3
"Time-to-first-successful-call, precisely"): computed live from
Auditability's own real event history, never self-reported. A
developer with zero recorded activity gets `None`, never a fabricated
zero -- the same insufficient-data-over-fabrication principle this
platform's other real-computed-Gauge services (Secrets and Credential
Management's rotation compliance, Billing and Metering's invoice
completeness) already apply.
"""
from __future__ import annotations

from sdk_and_developer_portal.core.domain import (
    AdoptionMetrics,
    AdoptionRateReport,
    DeveloperNotFoundError,
)
from sdk_and_developer_portal.core.ports import AuditabilityClient, PortalRepository
from sdk_and_developer_portal.telemetry.metrics import sdk_portal_adoption_rate


class AdoptionMetricsService:
    def __init__(self, repository: PortalRepository, auditability: AuditabilityClient) -> None:
        self._repository = repository
        self._auditability = auditability

    async def time_to_first_call(self, developer_id: str) -> AdoptionMetrics:
        developer = await self._repository.get_developer(developer_id)
        if developer is None:
            raise DeveloperNotFoundError(developer_id)

        total = await self._auditability.count_events(tenant_id=developer.tenant_id)
        if total == 0:
            return AdoptionMetrics(first_call_at=None, time_to_first_call_seconds=None)

        # Auditability's list order is newest-first, platform-wide -- the single oldest
        # event sits at offset `total - 1`. No page-size assumption, no full-history scan.
        first_call_at = await self._auditability.get_event_occurred_at(
            tenant_id=developer.tenant_id, offset=total - 1,
        )
        seconds = max((first_call_at - developer.created_at).total_seconds(), 0.0)
        return AdoptionMetrics(first_call_at=first_call_at, time_to_first_call_seconds=seconds)

    async def adoption_rate(self) -> AdoptionRateReport:
        developers = await self._repository.list_all_developers()
        total_developers = len(developers)
        if total_developers == 0:
            return AdoptionRateReport(adopted_count=0, total_developers=0, rate=None)

        adopted = 0
        for developer in developers:
            if await self._auditability.count_events(tenant_id=developer.tenant_id) > 0:
                adopted += 1

        rate = adopted / total_developers
        sdk_portal_adoption_rate.set(rate)
        return AdoptionRateReport(adopted_count=adopted, total_developers=total_developers, rate=rate)
