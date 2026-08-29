"""Workspace Service (independent architecture assessment §3.1, the
platform hierarchy control plane): register/suspend/reactivate/delete
for the second level of `Organisation -> Tenant -> Workspace ->
Environment`. Every workspace belongs to exactly one tenant, verified
to exist at registration -- the same "raises *NotFoundError for an
unknown parent" posture `TenantRegistryService.set_entitlements`
already established for entitlements.

suspend()/delete() cascade to every descendant Environment -- real
offboarding, not the "deliberately does not cascade" gap this
docstring used to flag. `cascade_environments` is exposed as its own
public method (not just an internal step of suspend()/delete()) so
`TenantRegistryService`'s own tenant-level cascade can invoke it
directly for a workspace that's already at (or past) the target status
independently of the tenant -- such a workspace is correctly skipped
for its *own* transition, but its environments still need to cascade,
which calling suspend()/delete() (guarded by `is_legal_hierarchy_
transition`) alone would silently skip.
"""
from __future__ import annotations

from multi_tenancy.core.domain import (
    HierarchyStatus,
    InvalidTransitionError,
    TenantNotFoundError,
    WorkspaceNotFoundError,
    WorkspaceRecord,
    is_legal_hierarchy_transition,
    new_id,
    now,
)
from multi_tenancy.core.environment_service import EnvironmentService
from multi_tenancy.core.ports import AuditabilityClient, MultiTenancyRepository

# One page at a time, rather than one unbounded list_environments call -- consistent
# with every other list endpoint in this module capping at 200.
_CASCADE_PAGE_SIZE = 200


class WorkspaceService:
    def __init__(self, repository: MultiTenancyRepository, auditability: AuditabilityClient) -> None:
        self._repository = repository
        self._auditability = auditability
        # Composed, not injected: EnvironmentService's own suspend()/delete() already
        # do exactly what a correct cascade needs -- a legality-checked transition plus
        # a real audit-emit -- so the cascade reuses that logic rather than hand-editing
        # child records and duplicating it.
        self._environments = EnvironmentService(repository, auditability)

    async def register(self, *, tenant_id: str, name: str, owner_identity_id: str | None = None) -> WorkspaceRecord:
        tenant = await self._repository.get_tenant(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(tenant_id)
        record = WorkspaceRecord(id=new_id(), tenant_id=tenant_id, name=name, owner_identity_id=owner_identity_id)
        created = await self._repository.create_workspace(record)
        await self._auditability.emit({
            "event": "workspace_created", "workspace_id": created.id, "tenant_id": tenant_id, "name": created.name,
        })
        return created

    async def get(self, workspace_id: str) -> WorkspaceRecord:
        record = await self._repository.get_workspace(workspace_id)
        if record is None:
            raise WorkspaceNotFoundError(workspace_id)
        return record

    async def list(
        self, *, tenant_id: str | None = None, status: HierarchyStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[WorkspaceRecord], int]:
        return await self._repository.list_workspaces(tenant_id=tenant_id, status=status, limit=limit, offset=offset)

    async def _transition(self, workspace_id: str, to_status: HierarchyStatus) -> WorkspaceRecord:
        ws = await self.get(workspace_id)
        if not is_legal_hierarchy_transition(ws.status, to_status):
            raise InvalidTransitionError(ws.status, to_status)
        from_status = ws.status
        ws.status = to_status
        ws.version += 1
        ws.updated_at = now()
        updated = await self._repository.update_workspace(ws)
        await self._auditability.emit({
            "event": "workspace_status_changed", "workspace_id": workspace_id, "tenant_id": ws.tenant_id,
            "from_status": from_status.value, "to_status": to_status.value,
        })
        return updated

    async def suspend(self, workspace_id: str, *, reason: str) -> WorkspaceRecord:
        updated = await self._transition(workspace_id, HierarchyStatus.SUSPENDED)
        await self.cascade_environments(workspace_id, HierarchyStatus.SUSPENDED, reason=reason)
        return updated

    async def reactivate(self, workspace_id: str) -> WorkspaceRecord:
        # Deliberately does not cascade -- see TenantRegistryService.reactivate's own
        # docstring for the identical reasoning one level up: an environment an
        # operator suspended independently of its workspace must not silently
        # reactivate just because the workspace did.
        return await self._transition(workspace_id, HierarchyStatus.ACTIVE)

    async def delete(self, workspace_id: str) -> WorkspaceRecord:
        updated = await self._transition(workspace_id, HierarchyStatus.DELETED)
        await self.cascade_environments(workspace_id, HierarchyStatus.DELETED, reason=None)
        return updated

    async def cascade_environments(
        self, workspace_id: str, to_status: HierarchyStatus, *, reason: str | None,
    ) -> None:
        """Transitions every Environment under `workspace_id` to
        `to_status`, skipping one already at (or past) it -- idempotent
        and safe to call more than once for the same workspace (e.g.
        once directly from suspend()/delete(), and once more from
        `TenantRegistryService`'s own cascade for a workspace whose own
        transition was skipped as already-legal-elsewhere)."""
        offset = 0
        while True:
            environments, total = await self._environments.list(
                workspace_id=workspace_id, status=None, limit=_CASCADE_PAGE_SIZE, offset=offset,
            )
            if not environments:
                break
            for environment in environments:
                if is_legal_hierarchy_transition(environment.status, to_status):
                    if to_status == HierarchyStatus.DELETED:
                        await self._environments.delete(environment.id)
                    else:
                        await self._environments.suspend(
                            environment.id, reason=reason or "cascaded from workspace suspension",
                        )
            offset += len(environments)
            if offset >= total:
                break
