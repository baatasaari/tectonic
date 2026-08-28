"""Environment Service (independent architecture assessment §3.1, the
platform hierarchy control plane): register/suspend/reactivate/delete
for the third level of `Organisation -> Tenant -> Workspace ->
Environment` -- the level real Agent Applications (Workflow Engine
runs, Conversational Engine sessions, ...) are ultimately scoped
under, once those modules adopt `environment_id`, which they don't
yet; see this module's README. Every environment belongs to exactly
one workspace, verified to exist at registration.
"""
from __future__ import annotations

from multi_tenancy.core.domain import (
    EnvironmentNotFoundError,
    EnvironmentRecord,
    HierarchyStatus,
    InvalidTransitionError,
    WorkspaceNotFoundError,
    is_legal_hierarchy_transition,
    new_id,
    now,
)
from multi_tenancy.core.ports import AuditabilityClient, MultiTenancyRepository


class EnvironmentService:
    def __init__(self, repository: MultiTenancyRepository, auditability: AuditabilityClient) -> None:
        self._repository = repository
        self._auditability = auditability

    async def register(
        self, *, workspace_id: str, name: str, kind: str = "development",
        region: str | None = None, owner_identity_id: str | None = None,
    ) -> EnvironmentRecord:
        workspace = await self._repository.get_workspace(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(workspace_id)
        record = EnvironmentRecord(
            id=new_id(), workspace_id=workspace_id, name=name, kind=kind, region=region,
            owner_identity_id=owner_identity_id,
        )
        created = await self._repository.create_environment(record)
        await self._auditability.emit({
            "event": "environment_created", "environment_id": created.id, "workspace_id": workspace_id,
            "name": created.name, "kind": created.kind,
        })
        return created

    async def get(self, environment_id: str) -> EnvironmentRecord:
        record = await self._repository.get_environment(environment_id)
        if record is None:
            raise EnvironmentNotFoundError(environment_id)
        return record

    async def list(
        self, *, workspace_id: str | None = None, status: HierarchyStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[EnvironmentRecord], int]:
        return await self._repository.list_environments(
            workspace_id=workspace_id, status=status, limit=limit, offset=offset,
        )

    async def _transition(self, environment_id: str, to_status: HierarchyStatus) -> EnvironmentRecord:
        env = await self.get(environment_id)
        if not is_legal_hierarchy_transition(env.status, to_status):
            raise InvalidTransitionError(env.status, to_status)
        from_status = env.status
        env.status = to_status
        env.version += 1
        env.updated_at = now()
        updated = await self._repository.update_environment(env)
        await self._auditability.emit({
            "event": "environment_status_changed", "environment_id": environment_id,
            "workspace_id": env.workspace_id, "from_status": from_status.value, "to_status": to_status.value,
        })
        return updated

    async def suspend(self, environment_id: str, *, reason: str) -> EnvironmentRecord:
        return await self._transition(environment_id, HierarchyStatus.SUSPENDED)

    async def reactivate(self, environment_id: str) -> EnvironmentRecord:
        return await self._transition(environment_id, HierarchyStatus.ACTIVE)

    async def delete(self, environment_id: str) -> EnvironmentRecord:
        return await self._transition(environment_id, HierarchyStatus.DELETED)
