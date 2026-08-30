"""Metering Service (LLD §2 sub-components, §Level 3 "Metering path"):
turns a pricing plan's resource keys into real, verified usage
quantities. `"llm.cost_usd"` is read from FinOps's own real cost
report (gated against the real `llm-gateway` module's own entitlement);
every other resource key is treated as a real `source_module` name --
both the Auditability event count *and* the entitlement check it's
gated behind -- and metered as "how many events did that module emit
to Auditability this period" -- FinOps's and Auditability's own real
numbers, never a usage-tracking pipeline this module invents.

Idempotent: every usage number this service persists goes through
`BillingRepository.upsert_usage_record`, keyed by `(tenant_id, period,
resource)` -- re-running `meter_tenant` for a period already metered
(a retried scheduler run, a re-triggered invoice generation) always
converges to the same ledger state instead of accumulating duplicate
rows that would double-count on the next invoice.
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
from billing_and_metering.core.ports import (
    AuditabilityClient,
    BillingRepository,
    FinOpsClient,
    MultiTenancyClient,
)
from billing_and_metering.telemetry.logging import get_logger
from billing_and_metering.telemetry.metrics import billing_metering_skipped_not_entitled_total

logger = get_logger(component="metering_service")

# LLM_COST_RESOURCE isn't itself a module name (see PricingPlanService's own
# entitlement-sync docstring) -- it's LLM Gateway's own real spend, so it's gated
# against that module's own service_name instead.
LLM_GATEWAY_MODULE_NAME = "llm-gateway"


class MeteringService:
    def __init__(
        self, repository: BillingRepository, finops: FinOpsClient, auditability: AuditabilityClient,
        multi_tenancy: MultiTenancyClient | None = None,
    ) -> None:
        self._repository = repository
        self._finops = finops
        self._auditability = auditability
        self._multi_tenancy = multi_tenancy

    async def meter_tenant(
        self, *, tenant_id: str, period: str, plan: PricingPlanRecord,
    ) -> tuple[list[MeteredUsageRecord], bool]:
        """Returns `(records, complete)` -- `complete` is `False` the
        moment any resource's real source is unreachable (a failed
        resource is skipped, never recorded as zero usage: not knowing
        and knowing-it-was-zero are different answers, and only the
        real one is ever persisted). A resource the tenant currently
        isn't entitled to is skipped too, but never marks `complete`
        false -- that's not missing data, it's a deliberate, known
        exclusion (see `_is_entitled`'s own docstring)."""
        start, end = period_window(period, now())
        records: list[MeteredUsageRecord] = []
        complete = True

        for resource in plan.unit_prices:
            module = LLM_GATEWAY_MODULE_NAME if resource == LLM_COST_RESOURCE else resource
            if not await self._is_entitled(tenant_id=tenant_id, module=module):
                logger.info("metering_skipped_not_entitled", tenant_id=tenant_id, resource=resource, module=module)
                billing_metering_skipped_not_entitled_total.labels(resource=resource).inc()
                continue

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
            records.append(await self._repository.upsert_usage_record(record))

        return records, complete

    async def _is_entitled(self, *, tenant_id: str, module: str) -> bool:
        """Real entitlement check via Multi-tenancy's own `gate()` --
        the same real `GET /tenants/{id}/gate?module=...` every
        `EntitlementGateMiddleware` in this platform already calls, so a
        tenant downgraded away from a module stops being billed for it
        on this metering run, not just blocked from calling it. `None`
        (no client configured) and a failed call both fail OPEN --
        meter as if entitled -- the same deliberate contrast with
        zero-trust auth this platform's entitlement checks always take:
        a commercial gate must never turn a Multi-tenancy outage into
        missed revenue on top of the outage itself."""
        if self._multi_tenancy is None:
            return True
        try:
            allowed, _reason = await self._multi_tenancy.gate(tenant_id=tenant_id, module=module)
            return allowed
        except Exception as exc:
            logger.warning("entitlement_gate_unavailable", tenant_id=tenant_id, module=module, error=str(exc))
            return True
