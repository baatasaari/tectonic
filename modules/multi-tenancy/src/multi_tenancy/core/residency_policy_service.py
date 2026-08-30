"""Residency Policy management (independent architecture assessment
§3.4 point 5: "quota, budget, residency, and risk policies permit
execution"). Real enforcement lives in `EnvironmentService.register`
(the actual point a `region` value is ever chosen) -- this service is
just the CRUD side, the same split `QuotaSetService`/
`QuotaEnforcementService` already established for quotas.
"""
from __future__ import annotations

from multi_tenancy.core.domain import ResidencyPolicy
from multi_tenancy.core.ports import MultiTenancyRepository


class ResidencyPolicyService:
    """Wholesale replace, the same pattern `QuotaSetService`/
    `TenantRegistryService.set_entitlements` already established: a
    policy change fully re-derives the whole `allowed_regions` list,
    never a field-by-field patch, so a region removed from the policy
    is never left reachable by a stale partial update."""

    def __init__(self, repository: MultiTenancyRepository) -> None:
        self._repository = repository

    async def get(self, tenant_id: str) -> ResidencyPolicy | None:
        return await self._repository.get_residency_policy(tenant_id)

    async def set_allowed_regions(self, tenant_id: str, *, allowed_regions: list[str]) -> ResidencyPolicy:
        return await self._repository.upsert_residency_policy(tenant_id=tenant_id, allowed_regions=allowed_regions)
