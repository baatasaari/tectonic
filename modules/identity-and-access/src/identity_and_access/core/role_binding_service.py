"""Role Binding Service (IAM v2 foundation): the missing lifecycle
operation on `IdentityRecord.role_names` -- before this, a role could
only ever be set once, at `IdentityRegistryService.register()` time.
There was no way to grant or revoke a single role on an already-
registered identity through this module's own API at all. `grant`/
`revoke` fix that, and both leave a durable `RoleBindingRecord` audit
row behind -- see that record's own docstring for why it's one row
per grant, updated in place on revoke, not a second row.
"""
from __future__ import annotations

from identity_and_access.core.domain import (
    IdentityNotFoundError,
    IdentityRecord,
    RoleBindingRecord,
    RoleNotFoundError,
    RoleNotGrantedError,
    new_id,
    now,
)
from identity_and_access.core.ports import IdentityAccessRepository


class RoleBindingService:
    def __init__(self, repository: IdentityAccessRepository) -> None:
        self._repository = repository

    async def grant(self, *, identity_id: str, role_name: str, granted_by: str = "") -> IdentityRecord:
        identity = await self._repository.get_identity(identity_id)
        if identity is None:
            raise IdentityNotFoundError(identity_id)
        # Resolved against this identity's own tenant (tenant-then-platform
        # fallback) -- a role that exists for some other tenant, and isn't a
        # platform default, can never be granted here.
        role = await self._repository.get_role(identity.tenant_id, role_name)
        if role is None:
            raise RoleNotFoundError(role_name)

        # Idempotent: granting an already-held role is a no-op on role_names
        # (a set, not a list one can hold duplicate membership in) and
        # doesn't write a second binding row -- the existing grant's own
        # granted_at/granted_by already answers "when/by whom", and a fresh
        # row would just be audit-trail noise for the same fact restated.
        if role_name in identity.role_names:
            return identity

        identity.role_names = [*identity.role_names, role_name]
        identity.updated_at = now()
        identity = await self._repository.update_identity(identity)

        binding = RoleBindingRecord(
            id=new_id(), tenant_id=identity.tenant_id, identity_id=identity_id,
            role_name=role_name, granted_by=granted_by,
        )
        await self._repository.create_role_binding(binding)
        return identity

    async def revoke(self, *, identity_id: str, role_name: str) -> IdentityRecord:
        identity = await self._repository.get_identity(identity_id)
        if identity is None:
            raise IdentityNotFoundError(identity_id)
        if role_name not in identity.role_names:
            raise RoleNotGrantedError(identity_id, role_name)

        identity.role_names = [r for r in identity.role_names if r != role_name]
        identity.updated_at = now()
        identity = await self._repository.update_identity(identity)

        active_binding = await self._repository.get_active_role_binding(
            identity_id=identity_id, role_name=role_name,
        )
        if active_binding is not None:
            await self._repository.revoke_role_binding(active_binding.id)
        return identity

    async def list_bindings(
        self, *, tenant_id: str | None = None, identity_id: str | None = None, role_name: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[RoleBindingRecord], int]:
        return await self._repository.list_role_bindings(
            tenant_id=tenant_id, identity_id=identity_id, role_name=role_name, limit=limit, offset=offset,
        )
