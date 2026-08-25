"""Metering Service (LLD §2 sub-components, §Level 3 "Metering path"):
turns a pricing plan's resource keys into real, verified usage
quantities. `"llm.cost_usd"` is read from FinOps's own real cost
report; every other resource key is treated as a real `source_module`
name and metered as "how many events did that module emit to
Auditability this period" -- FinOps's and Auditability's own real
numbers, never a usage-tracking pipeline this module invents.
"""
from __future__ import annotations

from billing_and_metering.core.domain import (
    LLM_COST_RESOURCE,
    MeteredUsageRecord,
    PricingPlanRecord,
    new_id,
    now,
)
from billing_and_metering.core.period import period_window
from billing_and_metering.core.ports import AuditabilityClient, BillingRepository, FinOpsClient
from billing_and_metering.telemetry.logging import get_logger

logger = get_logger(component="metering_service")


class MeteringService:
    def __init__(self, repository: BillingRepository, finops: FinOpsClient, auditability: AuditabilityClient) -> None:
        self._repository = repository
        self._finops = finops
        self._auditability = auditability

    async def meter_tenant(
        self, *, tenant_id: str, period: str, plan: PricingPlanRecord,
    ) -> tuple[list[MeteredUsageRecord], bool]:
        """Returns `(records, complete)` -- `complete` is `False` the
        moment any resource's real source is unreachable. A failed
        resource is skipped, never recorded as zero usage: not knowing
        and knowing-it-was-zero are different answers, and only the
        real one is ever persisted."""
        start, end = period_window(period, now())
        records: list[MeteredUsageRecord] = []
        complete = True

        for resource in plan.unit_prices:
            try:
                if resource == LLM_COST_RESOURCE:
                    quantity = await self._finops.get_total_cost(tenant_id=tenant_id, period=period)
                    source = "finops"
                else:
                    quantity = await self._auditability.count_events(
                        tenant_id=tenant_id, source_module=resource, occurred_after=start, occurred_before=end,
                    )
                    source = "auditability"
            except Exception as exc:
                logger.warning("metering_source_unavailable", resource=resource, error=str(exc))
                complete = False
                continue

            record = MeteredUsageRecord(
                id=new_id(), tenant_id=tenant_id, period=period, resource=resource, quantity=quantity, source=source,
            )
            records.append(await self._repository.create_usage_record(record))

        return records, complete
