"""Organisation Service (independent architecture assessment §3.1, the
platform hierarchy control plane): register/suspend/reactivate/delete
for the top level of `Organisation -> Tenant -> Workspace ->
Environment`. Same register/transition/audit shape
`TenantRegistryService` already established -- see that module's own
docstring for the reasoning behind the state machine and the
best-effort audit-emit posture.

Every transition takes the caller's `expected_version` (real
optimistic-concurrency control, not a decorative field -- the
repository does a real compare-and-swap; see `core/domain.py`'s
`OptimisticConcurrencyError` and `db/repository.py`'s
`_compare_and_swap`). Required, not optional: a caller that doesn't
know an object's current version has no business mutating it blind.
"""
from __future__ import annotations

from multi_tenancy.core.domain import (
    HierarchyStatus,
    InvalidTransitionError,
    OrganisationNotFoundError,
    OrganisationRecord,
    is_legal_hierarchy_transition,
    new_id,
    now,
)
from multi_tenancy.core.ports import AuditabilityClient, MultiTenancyRepository


class OrganisationService:
    def __init__(self, repository: MultiTenancyRepository, auditability: AuditabilityClient) -> None:
        self._repository = repository
        self._auditability = auditability

    async def register(self, *, name: str, owner_identity_id: str | None = None) -> OrganisationRecord:
        record = OrganisationRecord(id=new_id(), name=name, owner_identity_id=owner_identity_id)
        created = await self._repository.create_organisation(record)
        await self._auditability.emit({
            "event": "organisation_created", "organisation_id": created.id, "name": created.name,
        })
        return created

    async def get(self, organisation_id: str) -> OrganisationRecord:
        record = await self._repository.get_organisation(organisation_id)
        if record is None:
            raise OrganisationNotFoundError(organisation_id)
        return record

    async def list(
        self, *, status: HierarchyStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[OrganisationRecord], int]:
        return await self._repository.list_organisations(status=status, limit=limit, offset=offset)

    async def _transition(
        self, organisation_id: str, to_status: HierarchyStatus, *, expected_version: int,
    ) -> OrganisationRecord:
        org = await self.get(organisation_id)
        if not is_legal_hierarchy_transition(org.status, to_status):
            raise InvalidTransitionError(org.status, to_status)
        from_status = org.status
        org.status = to_status
        org.updated_at = now()
        updated = await self._repository.update_organisation(org, expected_version=expected_version)
        await self._auditability.emit({
            "event": "organisation_status_changed", "organisation_id": organisation_id,
            "from_status": from_status.value, "to_status": to_status.value,
        })
        return updated

    async def suspend(self, organisation_id: str, *, reason: str, expected_version: int) -> OrganisationRecord:
        # `reason` required but not stored, the same "an incident-shaped action requires
        # an explanation at the call site" posture TenantRegistryService.suspend uses.
        return await self._transition(organisation_id, HierarchyStatus.SUSPENDED, expected_version=expected_version)

    async def reactivate(self, organisation_id: str, *, expected_version: int) -> OrganisationRecord:
        return await self._transition(organisation_id, HierarchyStatus.ACTIVE, expected_version=expected_version)

    async def delete(self, organisation_id: str, *, expected_version: int) -> OrganisationRecord:
        # Deliberately does not cascade to member tenants -- a real offboarding saga
        # (suspend/export/erase every child resource in order) is separate, unbuilt
        # work; see this module's README.
        return await self._transition(organisation_id, HierarchyStatus.DELETED, expected_version=expected_version)
