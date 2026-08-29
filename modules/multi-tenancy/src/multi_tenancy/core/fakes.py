"""In-memory fakes for unit tests (LLD "Deployability and testability
contract")."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta
from typing import Any

from multi_tenancy.core.domain import (
    EnvironmentRecord,
    EventOutboxRecord,
    HierarchyStatus,
    IsolationProbeResult,
    OptimisticConcurrencyError,
    OrganisationRecord,
    OutboxEventStatus,
    QuotaSet,
    ResidencyPolicy,
    ResourceAllocation,
    ResourceAllocationStatus,
    TenantEntitlementRecord,
    TenantRecord,
    TenantStatus,
    WorkspaceRecord,
    now,
    quota_window_start,
)

_UNSET = object()


class InMemoryMultiTenancyRepository:
    def __init__(self) -> None:
        self.tenants: dict[str, TenantRecord] = {}
        self.probe_results: list[IsolationProbeResult] = []
        self.entitlements: dict[str, list[TenantEntitlementRecord]] = {}
        self.organisations: dict[str, OrganisationRecord] = {}
        self.workspaces: dict[str, WorkspaceRecord] = {}
        self.environments: dict[str, EnvironmentRecord] = {}
        self.quota_sets: dict[str, QuotaSet] = {}
        self.residency_policies: dict[str, ResidencyPolicy] = {}
        self.quota_counters: dict[tuple[str, str, datetime], float] = {}
        self.resource_allocations: dict[str, ResourceAllocation] = {}
        self.outbox: dict[str, EventOutboxRecord] = {}

    def _compare_and_swap(self, store: dict, record, *, expected_version: int):
        """Mirrors `db/repository.py`'s own real compare-and-swap so unit
        tests can prove `OptimisticConcurrencyError` behavior against
        this fake, not just against real Postgres in the integration
        tier -- a stale `expected_version` must raise here exactly the
        same way it does for real. Stores and returns a deep copy, never
        the caller's own passed-in object -- a real out-of-process
        datastore round trip wouldn't let the caller's further in-place
        mutation of their own reference silently corrupt what's stored,
        and this fake must not either (see `get_organisation`'s own
        docstring for the matching half of this isolation)."""
        current = store.get(record.id)
        if current is None or current.version != expected_version:
            raise OptimisticConcurrencyError(expected_version=expected_version)
        updated = copy.deepcopy(record)
        updated.version = expected_version + 1
        store[record.id] = updated
        return copy.deepcopy(updated)

    async def create_tenant(self, record: TenantRecord) -> TenantRecord:
        self.tenants[record.id] = record
        return record

    async def get_tenant(self, tenant_id: str) -> TenantRecord | None:
        return self.tenants.get(tenant_id)

    async def update_tenant(self, record: TenantRecord) -> TenantRecord:
        self.tenants[record.id] = record
        return record

    async def create_tenant_and_enqueue_event(
        self, record: TenantRecord, *, topic: str, envelope: dict[str, Any],
    ) -> TenantRecord:
        self.tenants[record.id] = copy.deepcopy(record)
        outbox_record = EventOutboxRecord(
            id=envelope["id"], topic=topic, tenant_id=envelope["tenant_id"], envelope=copy.deepcopy(envelope),
        )
        self.outbox[outbox_record.id] = outbox_record
        return copy.deepcopy(record)

    async def update_tenant_and_enqueue_event(
        self, record: TenantRecord, *, topic: str, envelope: dict[str, Any],
    ) -> TenantRecord:
        self.tenants[record.id] = copy.deepcopy(record)
        outbox_record = EventOutboxRecord(
            id=envelope["id"], topic=topic, tenant_id=envelope["tenant_id"], envelope=copy.deepcopy(envelope),
        )
        self.outbox[outbox_record.id] = outbox_record
        return copy.deepcopy(record)

    async def replace_entitlements(
        self, *, tenant_id: str, module_names: list[str],
    ) -> list[TenantEntitlementRecord]:
        records = [TenantEntitlementRecord(tenant_id=tenant_id, module_name=name) for name in module_names]
        self.entitlements[tenant_id] = records
        tenant = self.tenants.get(tenant_id)
        if tenant is not None:
            tenant.entitlements_configured_at = now()
        return records

    async def list_entitlements(self, tenant_id: str) -> list[TenantEntitlementRecord]:
        return list(self.entitlements.get(tenant_id, []))

    async def list_tenants(
        self, *, status: TenantStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[TenantRecord], int]:
        results = list(self.tenants.values())
        if status is not None:
            results = [t for t in results if t.status == status]
        results = sorted(results, key=lambda t: t.created_at)
        return results[offset:offset + limit], len(results)

    async def create_probe_result(self, record: IsolationProbeResult) -> IsolationProbeResult:
        self.probe_results.append(record)
        return record

    async def list_probe_results(
        self, *, tenant_id: str | None = None, target_name: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[IsolationProbeResult], int]:
        results = list(self.probe_results)
        if tenant_id is not None:
            results = [r for r in results if r.tenant_id == tenant_id]
        if target_name is not None:
            results = [r for r in results if r.target_name == target_name]
        results = sorted(results, key=lambda r: r.checked_at, reverse=True)
        return results[offset:offset + limit], len(results)

    # --- Organisation / Workspace / Environment ---

    async def create_organisation(self, record: OrganisationRecord) -> OrganisationRecord:
        self.organisations[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_organisation(self, organisation_id: str) -> OrganisationRecord | None:
        # A deep copy, not the live stored reference -- callers (every _transition
        # method in this module) mutate the record they get back in place before
        # calling update_*; if this returned the same object the store holds, that
        # in-place mutation would silently corrupt the "canonical" state ahead of --
        # and regardless of the outcome of -- the real compare-and-swap in update_*.
        # A real out-of-process datastore round trip could never alias like this.
        record = self.organisations.get(organisation_id)
        return copy.deepcopy(record) if record is not None else None

    async def update_organisation(self, record: OrganisationRecord, *, expected_version: int) -> OrganisationRecord:
        return self._compare_and_swap(self.organisations, record, expected_version=expected_version)

    async def list_organisations(
        self, *, status: HierarchyStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[OrganisationRecord], int]:
        results = list(self.organisations.values())
        if status is not None:
            results = [o for o in results if o.status == status]
        results = sorted(results, key=lambda o: o.created_at)
        return [copy.deepcopy(o) for o in results[offset:offset + limit]], len(results)

    async def create_workspace(self, record: WorkspaceRecord) -> WorkspaceRecord:
        self.workspaces[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        # See get_organisation's own docstring for why this is a deep copy.
        record = self.workspaces.get(workspace_id)
        return copy.deepcopy(record) if record is not None else None

    async def update_workspace(self, record: WorkspaceRecord, *, expected_version: int) -> WorkspaceRecord:
        return self._compare_and_swap(self.workspaces, record, expected_version=expected_version)

    async def list_workspaces(
        self, *, tenant_id: str | None = None, status: HierarchyStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[WorkspaceRecord], int]:
        results = list(self.workspaces.values())
        if tenant_id is not None:
            results = [w for w in results if w.tenant_id == tenant_id]
        if status is not None:
            results = [w for w in results if w.status == status]
        results = sorted(results, key=lambda w: w.created_at)
        return [copy.deepcopy(w) for w in results[offset:offset + limit]], len(results)

    async def create_environment(self, record: EnvironmentRecord) -> EnvironmentRecord:
        self.environments[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_environment(self, environment_id: str) -> EnvironmentRecord | None:
        # See get_organisation's own docstring for why this is a deep copy.
        record = self.environments.get(environment_id)
        return copy.deepcopy(record) if record is not None else None

    async def update_environment(self, record: EnvironmentRecord, *, expected_version: int) -> EnvironmentRecord:
        return self._compare_and_swap(self.environments, record, expected_version=expected_version)

    async def list_environments(
        self, *, workspace_id: str | None = None, status: HierarchyStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[EnvironmentRecord], int]:
        results = list(self.environments.values())
        if workspace_id is not None:
            results = [e for e in results if e.workspace_id == workspace_id]
        if status is not None:
            results = [e for e in results if e.status == status]
        results = sorted(results, key=lambda e: e.created_at)
        return [copy.deepcopy(e) for e in results[offset:offset + limit]], len(results)

    # --- Quota Set / real-time quota enforcement ---

    async def get_quota_set(self, tenant_id: str) -> QuotaSet | None:
        return self.quota_sets.get(tenant_id)

    async def upsert_quota_set(self, *, tenant_id: str, limits: dict[str, float]) -> QuotaSet:
        existing = self.quota_sets.get(tenant_id)
        version = existing.version + 1 if existing else 1
        record = QuotaSet(tenant_id=tenant_id, limits=dict(limits), configured_at=now(), version=version)
        self.quota_sets[tenant_id] = record
        return record

    async def get_residency_policy(self, tenant_id: str) -> ResidencyPolicy | None:
        return self.residency_policies.get(tenant_id)

    async def upsert_residency_policy(self, *, tenant_id: str, allowed_regions: list[str]) -> ResidencyPolicy:
        existing = self.residency_policies.get(tenant_id)
        version = existing.version + 1 if existing else 1
        record = ResidencyPolicy(
            tenant_id=tenant_id, allowed_regions=list(allowed_regions), configured_at=now(), version=version,
        )
        self.residency_policies[tenant_id] = record
        return record

    async def increment_quota_counter(
        self, *, tenant_id: str, resource_class: str, amount: float, window_seconds: int, now: datetime,
    ) -> float:
        window_start = quota_window_start(now, window_seconds)
        key = (tenant_id, resource_class, window_start)
        self.quota_counters[key] = self.quota_counters.get(key, 0.0) + amount
        return self.quota_counters[key]

    # --- Resource Allocation ---

    async def create_resource_allocation(self, record: ResourceAllocation) -> ResourceAllocation:
        self.resource_allocations[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_resource_allocation(self, allocation_id: str) -> ResourceAllocation | None:
        # See get_organisation's own docstring for why this is a deep copy.
        record = self.resource_allocations.get(allocation_id)
        return copy.deepcopy(record) if record is not None else None

    async def update_resource_allocation(
        self, record: ResourceAllocation, *, expected_version: int,
    ) -> ResourceAllocation:
        return self._compare_and_swap(self.resource_allocations, record, expected_version=expected_version)

    async def get_active_resource_allocation(self, environment_id: str) -> ResourceAllocation | None:
        candidates = [
            r for r in self.resource_allocations.values()
            if r.environment_id == environment_id and r.status == ResourceAllocationStatus.ACTIVE
        ]
        if not candidates:
            return None
        return copy.deepcopy(max(candidates, key=lambda r: r.updated_at))

    async def list_resource_allocations(
        self, *, environment_id: str | None = None, status: ResourceAllocationStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[ResourceAllocation], int]:
        results = list(self.resource_allocations.values())
        if environment_id is not None:
            results = [r for r in results if r.environment_id == environment_id]
        if status is not None:
            results = [r for r in results if r.status == status]
        results = sorted(results, key=lambda r: r.created_at, reverse=True)
        return [copy.deepcopy(r) for r in results[offset:offset + limit]], len(results)

    # --- Event outbox relay (core/outbox_worker.py) ---

    async def claim_next_outbox_event(self, worker_id: str, lease_seconds: int) -> EventOutboxRecord | None:
        moment = now()
        candidates = [
            e for e in self.outbox.values()
            if e.status == OutboxEventStatus.PENDING and (e.lease_expires_at is None or e.lease_expires_at < moment)
        ]
        if not candidates:
            return None
        oldest = min(candidates, key=lambda e: e.created_at)
        oldest.worker_id = worker_id
        oldest.attempts += 1
        oldest.lease_expires_at = moment + timedelta(seconds=lease_seconds)
        return copy.deepcopy(oldest)

    async def mark_outbox_event_published(self, event_id: str) -> None:
        record = self.outbox.get(event_id)
        if record is None:
            return
        record.status = OutboxEventStatus.PUBLISHED
        record.published_at = now()
        record.lease_expires_at = None

    async def requeue_outbox_event_for_retry(self, event_id: str, *, error: str) -> None:
        record = self.outbox.get(event_id)
        if record is None:
            return
        record.lease_expires_at = None
        record.last_error = error

    async def fail_exhausted_outbox_events(self, max_attempts: int) -> int:
        count = 0
        for record in self.outbox.values():
            if record.status == OutboxEventStatus.PENDING and record.attempts >= max_attempts:
                record.status = OutboxEventStatus.FAILED
                record.last_error = f"exceeded max attempts ({max_attempts})"
                count += 1
        return count

    async def force_expire_stale_outbox_leases(self) -> int:
        moment = now()
        count = 0
        for record in self.outbox.values():
            if (
                record.status == OutboxEventStatus.PENDING
                and record.lease_expires_at is not None
                and record.lease_expires_at > moment
            ):
                record.lease_expires_at = moment
                count += 1
        return count


class InMemoryEventPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        self.published.append((topic, event))


class StubAuditabilityClient:
    """Records every emitted event and never raises -- mirrors
    `HTTPAuditabilityClient.emit`'s own best-effort contract, so a
    caller test never needs a try/except around it."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(self, event: dict[str, Any]) -> None:
        self.events.append(event)


class StubTenantScopedListClient:
    """`items` is the raw list this stub returns as-is -- pass items whose
    own `tenant_id` deliberately doesn't match the probed tenant to
    exercise the breach-detection path. `raise_error=True` simulates an
    unreachable target."""

    def __init__(self, *, items: list[dict[str, Any]] | object = _UNSET, raise_error: bool = False) -> None:
        self.calls: list[dict] = []
        self._items = [] if items is _UNSET else items
        self._raise_error = raise_error

    async def list_tenant_scoped_items(self, *, tenant_id: str) -> list[dict[str, Any]]:
        self.calls.append({"tenant_id": tenant_id})
        if self._raise_error:
            raise RuntimeError("target is down")
        return self._items


__all__ = [
    "InMemoryEventPublisher", "InMemoryMultiTenancyRepository", "StubAuditabilityClient",
    "StubTenantScopedListClient",
]
