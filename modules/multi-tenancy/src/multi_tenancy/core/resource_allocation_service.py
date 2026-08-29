"""Resource Allocation Service (independent architecture assessment
§5.2 "Resource allocation and quota change"): the environment-scoped
canonical allocation object, with a real request -> automated-or-
manual-approval -> active lifecycle, not just a CRUD data bag.
"""
from __future__ import annotations

from multi_tenancy.core.domain import (
    EnvironmentNotFoundError,
    InvalidTransitionError,
    ResourceAllocation,
    ResourceAllocationNotFoundError,
    ResourceAllocationStatus,
    new_id,
    now,
)
from multi_tenancy.core.ports import AuditabilityClient, MultiTenancyRepository

# §5.2: "submit requested quota -> automated policy decision -> approval if
# threshold exceeded". 20% is this platform's own default threshold, not the
# assessment's -- there's no prescribed number, and a real deployment would
# likely make this tenant-tier-configurable; that's separate, unbuilt work.
DEFAULT_AUTO_APPROVE_INCREASE_RATIO = 0.20


class ResourceAllocationService:
    def __init__(
        self, repository: MultiTenancyRepository, auditability: AuditabilityClient,
        *, auto_approve_increase_ratio: float = DEFAULT_AUTO_APPROVE_INCREASE_RATIO,
    ) -> None:
        self._repository = repository
        self._auditability = auditability
        self._auto_approve_increase_ratio = auto_approve_increase_ratio

    async def request_change(
        self, *, environment_id: str, resources: dict[str, float],
        reserved_capacity: bool = False, requested_by: str | None = None,
    ) -> ResourceAllocation:
        env = await self._repository.get_environment(environment_id)
        if env is None:
            raise EnvironmentNotFoundError(environment_id)

        current = await self._repository.get_active_resource_allocation(environment_id)
        record = ResourceAllocation(
            id=new_id(), environment_id=environment_id, resources=dict(resources),
            reserved_capacity=reserved_capacity, requested_by=requested_by,
        )
        if self._within_auto_approve_threshold(current, resources):
            record.status = ResourceAllocationStatus.ACTIVE
            record.approved_by = "auto-policy"

        created = await self._repository.create_resource_allocation(record)
        await self._auditability.emit({
            "event": "resource_allocation_requested", "allocation_id": created.id,
            "environment_id": environment_id, "resources": resources, "status": created.status.value,
        })
        if created.status == ResourceAllocationStatus.ACTIVE:
            await self._auditability.emit({
                "event": "resource_allocation_auto_approved", "allocation_id": created.id,
                "environment_id": environment_id,
            })
        return created

    def _within_auto_approve_threshold(
        self, current: ResourceAllocation | None, requested: dict[str, float],
    ) -> bool:
        """A fresh environment with no prior active allocation always
        needs explicit approval -- there's no baseline to compare an
        increase against. Otherwise: every resource-class value that
        goes up must move by no more than `auto_approve_increase_ratio`
        relative to its current value; a resource class the environment
        never had before also requires approval, not a free pass (it
        isn't an "increase" over anything). A decrease, or no change, is
        always fine -- this threshold exists to gate growth in cost and
        capacity, not to gate giving resources back."""
        if current is None:
            return False
        for resource_class, requested_value in requested.items():
            current_value = current.resources.get(resource_class)
            if current_value is None:
                return False
            if requested_value <= current_value:
                continue
            increase_ratio = (
                (requested_value - current_value) / current_value if current_value else float("inf")
            )
            if increase_ratio > self._auto_approve_increase_ratio:
                return False
        return True

    async def get(self, allocation_id: str) -> ResourceAllocation:
        record = await self._repository.get_resource_allocation(allocation_id)
        if record is None:
            raise ResourceAllocationNotFoundError(allocation_id)
        return record

    async def list(
        self, *, environment_id: str | None = None, status: ResourceAllocationStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[ResourceAllocation], int]:
        return await self._repository.list_resource_allocations(
            environment_id=environment_id, status=status, limit=limit, offset=offset,
        )

    async def approve(self, allocation_id: str, *, approved_by: str, expected_version: int) -> ResourceAllocation:
        # expected_version guards the exact race this endpoint exists for: two
        # reviewers deciding on the same REQUESTED allocation nearly simultaneously,
        # one approving and one rejecting. The in-process `status != REQUESTED` check
        # below only catches a stale read within *this* call; the real protection is
        # the repository's compare-and-swap against expected_version, which the second
        # of two racing decisions always loses (a real OptimisticConcurrencyError, not
        # a silently-overwritten decision).
        record = await self.get(allocation_id)
        if record.status != ResourceAllocationStatus.REQUESTED:
            raise InvalidTransitionError(record.status, ResourceAllocationStatus.ACTIVE)
        record.status = ResourceAllocationStatus.ACTIVE
        record.approved_by = approved_by
        record.updated_at = now()
        updated = await self._repository.update_resource_allocation(record, expected_version=expected_version)
        await self._auditability.emit({
            "event": "resource_allocation_approved", "allocation_id": allocation_id,
            "environment_id": record.environment_id, "approved_by": approved_by,
        })
        return updated

    async def reject(self, allocation_id: str, *, reason: str, expected_version: int) -> ResourceAllocation:
        record = await self.get(allocation_id)
        if record.status != ResourceAllocationStatus.REQUESTED:
            raise InvalidTransitionError(record.status, ResourceAllocationStatus.REJECTED)
        record.status = ResourceAllocationStatus.REJECTED
        record.rejection_reason = reason
        record.updated_at = now()
        updated = await self._repository.update_resource_allocation(record, expected_version=expected_version)
        await self._auditability.emit({
            "event": "resource_allocation_rejected", "allocation_id": allocation_id,
            "environment_id": record.environment_id, "reason": reason,
        })
        return updated
