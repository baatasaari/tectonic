"""Quota Set management and real-time quota enforcement (independent
architecture assessment §5.2 "Resource allocation and quota change",
§3.4 point 5: "quota, budget, residency, and risk policies permit
execution")."""
from __future__ import annotations

from datetime import datetime

from multi_tenancy.core.domain import QuotaCheckResult, QuotaSet, now, resource_class_window_seconds
from multi_tenancy.core.ports import MultiTenancyRepository


class QuotaSetService:
    """Wholesale replace, the same pattern `TenantRegistryService.
    set_entitlements` already established: a plan/tier change fully
    re-derives the whole `limits` dict, never a field-by-field patch, so
    no stale limit survives a downgrade."""

    def __init__(self, repository: MultiTenancyRepository) -> None:
        self._repository = repository

    async def get(self, tenant_id: str) -> QuotaSet | None:
        return await self._repository.get_quota_set(tenant_id)

    async def set_limits(self, tenant_id: str, *, limits: dict[str, float]) -> QuotaSet:
        return await self._repository.upsert_quota_set(tenant_id=tenant_id, limits=limits)


class QuotaEnforcementService:
    """The real-time decision every module wanting to enforce a quota
    before doing expensive work is meant to call -- the quota analogue
    of `TenantRegistryService.gate`. Two different enforcement shapes
    for two different kinds of resource class, chosen by name
    convention (`resource_class_window_seconds`):

    - **Rate-shaped** classes (name ends `_per_minute`, `_per_second`,
      `_per_hour`, `_per_day`, or `_daily` -- e.g.
      `"requests_per_minute"`, `"tokens_per_minute"`): this module owns
      the counter itself. `check_and_consume` increments a real
      fixed-window counter and checks the new total against the limit
      in one atomic repository call (consume-then-check, not
      check-then-consume) -- correct under concurrent callers, and a
      denied call still counts as an attempt, which is the standard,
      abuse-resistant shape for a rate limiter (a caller that retries
      instantly on denial doesn't get free extra attempts).
    - **Capacity-shaped** classes (everything else, e.g.
      `"storage_gb"`, `"vector_count"`): this module does NOT track
      live usage for these -- the owning module is the real source of
      truth for its own current usage, the same don't-duplicate-
      another-module's-state posture FinOps already takes reading
      Billing's real spend rather than re-deriving it. The caller
      supplies `current_usage`; this is a stateless ceiling check, not
      a counter, and raises `ValueError` if `current_usage` is missing.

    An unconfigured tenant (no `QuotaSet` ever set) is unlimited for
    every resource class -- the same rollout-safety default
    `TenantRegistryService.gate` already established for entitlements:
    shipping quota enforcement must never silently start throttling a
    tenant that predates it.
    """

    def __init__(self, repository: MultiTenancyRepository) -> None:
        self._repository = repository

    async def check_and_consume(
        self, tenant_id: str, *, resource_class: str, amount: float = 1.0,
        current_usage: float | None = None, at: datetime | None = None,
    ) -> QuotaCheckResult:
        quota_set = await self._repository.get_quota_set(tenant_id)
        limit = quota_set.limits.get(resource_class) if quota_set is not None else None
        if limit is None:
            return QuotaCheckResult(
                allowed=True, resource_class=resource_class, limit=None, used=0.0, remaining=None,
                reason="no quota configured for this resource class",
            )

        window_seconds = resource_class_window_seconds(resource_class)
        if window_seconds is not None:
            used = await self._repository.increment_quota_counter(
                tenant_id=tenant_id, resource_class=resource_class, amount=amount,
                window_seconds=window_seconds, now=at or now(),
            )
        else:
            if current_usage is None:
                raise ValueError(
                    f"current_usage is required to check the capacity-shaped resource class {resource_class!r}"
                )
            used = current_usage + amount

        allowed = used <= limit
        return QuotaCheckResult(
            allowed=allowed, resource_class=resource_class, limit=limit, used=used,
            remaining=max(limit - used, 0.0),
            reason="active" if allowed else f"quota exceeded for {resource_class}",
        )
