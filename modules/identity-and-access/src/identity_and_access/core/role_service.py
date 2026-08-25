"""Role Service (LLD §2 sub-components): create/get/list roles, each a
named bundle of real scope strings."""
from __future__ import annotations

from identity_and_access.core.domain import RoleNotFoundError, RoleRecord
from identity_and_access.core.ports import IdentityAccessRepository


class RoleService:
    def __init__(self, repository: IdentityAccessRepository) -> None:
        self._repository = repository

    async def create(self, *, name: str, scopes: list[str], description: str = "") -> RoleRecord:
        record = RoleRecord(name=name, scopes=scopes, description=description)
        return await self._repository.create_role(record)

    async def get(self, name: str) -> RoleRecord:
        record = await self._repository.get_role(name)
        if record is None:
            raise RoleNotFoundError(name)
        return record

    async def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list[RoleRecord], int]:
        return await self._repository.list_roles(limit=limit, offset=offset)
