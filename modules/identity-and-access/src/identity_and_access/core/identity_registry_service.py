"""Identity Registry Service (LLD §2 sub-components, §Level 3 "The
identity lifecycle state machine"): register/revoke/reinstate. Every
role assigned at registration must already exist -- an identity is
never created pointing at a role that doesn't.
"""
from __future__ import annotations

from identity_and_access.core.domain import (
    IdentityNotFoundError,
    IdentityRecord,
    IdentityStatus,
    IdentityType,
    InvalidTransitionError,
    RoleNotFoundError,
    is_legal_transition,
    new_id,
    now,
)
from identity_and_access.core.ports import IdentityAccessRepository


class IdentityRegistryService:
    def __init__(self, repository: IdentityAccessRepository) -> None:
        self._repository = repository

    async def register(
        self, *, tenant_id: str, name: str, type: IdentityType = IdentityType.AGENT,
        role_names: list[str] | None = None,
    ) -> IdentityRecord:
        role_names = role_names or []
        for role_name in role_names:
            if await self._repository.get_role(tenant_id, role_name) is None:
                raise RoleNotFoundError(role_name)

        record = IdentityRecord(id=new_id(), tenant_id=tenant_id, name=name, type=type, role_names=role_names)
        return await self._repository.create_identity(record)

    async def get(self, identity_id: str) -> IdentityRecord:
        record = await self._repository.get_identity(identity_id)
        if record is None:
            raise IdentityNotFoundError(identity_id)
        return record

    async def list(
        self, *, tenant_id: str | None = None, status: IdentityStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[IdentityRecord], int]:
        return await self._repository.list_identities(tenant_id=tenant_id, status=status, limit=limit, offset=offset)

    async def _transition(self, identity_id: str, to_status: IdentityStatus) -> IdentityRecord:
        identity = await self.get(identity_id)
        if not is_legal_transition(identity.status, to_status):
            raise InvalidTransitionError(identity.status, to_status)
        identity.status = to_status
        identity.updated_at = now()
        return await self._repository.update_identity(identity)

    async def revoke(self, identity_id: str) -> IdentityRecord:
        return await self._transition(identity_id, IdentityStatus.REVOKED)

    async def reinstate(self, identity_id: str) -> IdentityRecord:
        return await self._transition(identity_id, IdentityStatus.ACTIVE)
