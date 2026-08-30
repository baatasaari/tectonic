"""Group Service: CRUD for IdP-group -> default-role mappings
(`core/domain.py::GroupRecord`). `OidcFederationService` reads these
(by `find_group_by_external_id`) to compute an identity's
`federated_role_names` on every login; nothing here mutates an
identity."""
from __future__ import annotations

from identity_and_access.core.domain import GroupNotFoundError, GroupRecord, new_id
from identity_and_access.core.ports import IdentityAccessRepository


class GroupService:
    def __init__(self, repository: IdentityAccessRepository) -> None:
        self._repository = repository

    async def register(
        self, *, tenant_id: str, provider_id: str, external_id: str, name: str,
        default_role_names: list[str] | None = None,
    ) -> GroupRecord:
        record = GroupRecord(
            id=new_id(), tenant_id=tenant_id, provider_id=provider_id, external_id=external_id, name=name,
            default_role_names=default_role_names or [],
        )
        return await self._repository.create_group(record)

    async def get(self, group_id: str) -> GroupRecord:
        record = await self._repository.get_group(group_id)
        if record is None:
            raise GroupNotFoundError(group_id)
        return record

    async def list(
        self, *, tenant_id: str | None = None, provider_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[GroupRecord], int]:
        return await self._repository.list_groups(tenant_id=tenant_id, provider_id=provider_id, limit=limit, offset=offset)

    async def set_default_role_names(self, group_id: str, role_names: list[str]) -> GroupRecord:
        record = await self.get(group_id)
        record.default_role_names = role_names
        updated = await self._repository.update_group(record)
        for identity_id in updated.member_identity_ids:
            await self._recompute_federated_roles(tenant_id=updated.tenant_id, identity_id=identity_id)
        return updated

    async def set_members(self, group_id: str, member_identity_ids: list[str]) -> GroupRecord:
        """Wholesale-replaces this group's membership (SCIM's own PUT/PATCH
        contract is push-based, not incremental deltas the caller expects
        us to reconcile) and recomputes `federated_role_names` for every
        identity whose membership changed either way -- an identity
        removed from the last group granting a role loses that role
        immediately, the same live-effect posture
        AuthorizationService.authorize already takes for revocation."""
        record = await self.get(group_id)
        affected = set(record.member_identity_ids) | set(member_identity_ids)
        record.member_identity_ids = member_identity_ids
        updated = await self._repository.update_group(record)
        for identity_id in affected:
            await self._recompute_federated_roles(tenant_id=updated.tenant_id, identity_id=identity_id)
        return updated

    async def _recompute_federated_roles(self, *, tenant_id: str, identity_id: str) -> None:
        identity = await self._repository.get_identity(identity_id)
        if identity is None:
            return
        groups, _ = await self._repository.list_groups(tenant_id=tenant_id, limit=10_000)
        role_names: set[str] = set()
        for group in groups:
            if identity_id in group.member_identity_ids:
                role_names.update(group.default_role_names)
        identity.federated_role_names = sorted(role_names)
        await self._repository.update_identity(identity)
