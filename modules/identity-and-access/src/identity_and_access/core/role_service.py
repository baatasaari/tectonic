"""Role Service (LLD §2 sub-components, extended for the IAM v2
foundation): create/get/list roles, each a named bundle of real scope
strings, now tenant-scoped (see domain.py's PLATFORM_TENANT_ID
docstring for why)."""
from __future__ import annotations

from identity_and_access.core.domain import (
    PLATFORM_TENANT_ID,
    RoleAlreadyExistsError,
    RoleNotFoundError,
    RoleRecord,
)
from identity_and_access.core.ports import IdentityAccessRepository


class RoleService:
    def __init__(self, repository: IdentityAccessRepository) -> None:
        self._repository = repository

    async def create(
        self, *, tenant_id: str = PLATFORM_TENANT_ID, name: str, scopes: list[str], description: str = "",
    ) -> RoleRecord:
        # Explicit pre-check for a clean, typed error (RoleAlreadyExistsError,
        # not a raw IntegrityError leaking out of the DB layer) -- the same
        # check-then-create style this module already uses for role-existence
        # validation in identity_registry_service.register(). A real race
        # between two concurrent creates of the same (tenant_id, name) is
        # still caught by the table's own unique constraint, just surfaced
        # as a 500 rather than this clean 409 in that narrow window -- an
        # accepted, documented simplification, not a new class of risk.
        if await self._repository.get_role_by_tenant_and_name(tenant_id, name) is not None:
            raise RoleAlreadyExistsError(tenant_id, name)
        record = RoleRecord(tenant_id=tenant_id, name=name, scopes=scopes, description=description)
        return await self._repository.create_role(record)

    async def get(self, *, tenant_id: str, name: str) -> RoleRecord:
        """Tenant-then-platform-fallback resolution -- see
        IdentityAccessRepository.get_role's own docstring."""
        record = await self._repository.get_role(tenant_id, name)
        if record is None:
            raise RoleNotFoundError(name)
        return record

    async def list(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[RoleRecord], int]:
        """Exact tenant_id filter, no platform-role injection -- a tenant
        wanting both its own roles and the platform defaults calls this
        twice (once with its own tenant_id, once with
        domain.PLATFORM_TENANT_ID). Keeps pagination exact and simple
        rather than merging two paginated sources; see this module's
        README for the fuller reasoning."""
        return await self._repository.list_roles(tenant_id=tenant_id, limit=limit, offset=offset)
