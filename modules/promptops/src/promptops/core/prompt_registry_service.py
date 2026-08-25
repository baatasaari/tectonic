"""Prompt Registry (LLD §2 sub-components): register/list/get prompt
template versions."""
from __future__ import annotations

from promptops.core.domain import PromptVersionNotFoundError, PromptVersionRecord, new_id
from promptops.core.ports import PromptOpsRepository


class PromptRegistryService:
    def __init__(self, repository: PromptOpsRepository) -> None:
        self._repository = repository

    async def register(self, *, tenant_id: str, prompt_name: str, version: str, template: str) -> PromptVersionRecord:
        record = PromptVersionRecord(
            id=new_id(), tenant_id=tenant_id, prompt_name=prompt_name, version=version, template=template,
        )
        return await self._repository.create_prompt_version(record)

    async def get(self, prompt_version_id: str) -> PromptVersionRecord:
        record = await self._repository.get_prompt_version(prompt_version_id)
        if record is None:
            raise PromptVersionNotFoundError(prompt_version_id)
        return record

    async def list(
        self, *, tenant_id: str | None = None, prompt_name: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[PromptVersionRecord], int]:
        return await self._repository.list_prompt_versions(
            tenant_id=tenant_id, prompt_name=prompt_name, limit=limit, offset=offset,
        )
