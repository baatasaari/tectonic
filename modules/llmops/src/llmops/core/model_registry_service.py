"""Model Registry Service (LLD §2 sub-components): register a model
version, list version history.
"""
from __future__ import annotations

from llmops.core.domain import ModelVersionNotFoundError, ModelVersionRecord, new_id
from llmops.core.ports import LLMOpsRepository


class ModelRegistryService:
    def __init__(self, repository: LLMOpsRepository) -> None:
        self._repository = repository

    async def register(self, *, tenant_id: str, model_name: str, version: str, artifact_ref: str) -> ModelVersionRecord:
        record = ModelVersionRecord(
            id=new_id(), tenant_id=tenant_id, model_name=model_name, version=version, artifact_ref=artifact_ref,
        )
        return await self._repository.create_model_version(record)

    async def get(self, model_version_id: str) -> ModelVersionRecord:
        record = await self._repository.get_model_version(model_version_id)
        if record is None:
            raise ModelVersionNotFoundError(model_version_id)
        return record

    async def list(
        self, *, tenant_id: str | None = None, model_name: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ModelVersionRecord], int]:
        return await self._repository.list_model_versions(tenant_id=tenant_id, model_name=model_name, limit=limit, offset=offset)
