"""In-memory fakes for unit tests (LLD "Deployability and testability
contract")."""
from __future__ import annotations

from typing import Any

from llmops.core.domain import DeploymentRecord, DeploymentStage, ModelVersionRecord


class InMemoryLLMOpsRepository:
    def __init__(self) -> None:
        self.model_versions: dict[str, ModelVersionRecord] = {}
        self.deployments: dict[str, DeploymentRecord] = {}

    async def create_model_version(self, record: ModelVersionRecord) -> ModelVersionRecord:
        self.model_versions[record.id] = record
        return record

    async def get_model_version(self, model_version_id: str) -> ModelVersionRecord | None:
        return self.model_versions.get(model_version_id)

    async def update_model_version(self, record: ModelVersionRecord) -> ModelVersionRecord:
        self.model_versions[record.id] = record
        return record

    async def list_model_versions(
        self, *, tenant_id: str | None = None, model_name: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ModelVersionRecord], int]:
        results = list(self.model_versions.values())
        if tenant_id is not None:
            results = [v for v in results if v.tenant_id == tenant_id]
        if model_name is not None:
            results = [v for v in results if v.model_name == model_name]
        results = sorted(results, key=lambda v: v.created_at)
        return results[offset:offset + limit], len(results)

    async def create_deployment(self, record: DeploymentRecord) -> DeploymentRecord:
        self.deployments[record.id] = record
        return record

    async def get_deployment(self, deployment_id: str) -> DeploymentRecord | None:
        return self.deployments.get(deployment_id)

    async def update_deployment(self, record: DeploymentRecord) -> DeploymentRecord:
        self.deployments[record.id] = record
        return record

    async def get_active_deployment(self, *, tenant_id: str, model_name: str, target: str) -> DeploymentRecord | None:
        for deployment in self.deployments.values():
            if (
                deployment.tenant_id == tenant_id and deployment.model_name == model_name
                and deployment.target == target and deployment.stage == DeploymentStage.ACTIVE
            ):
                return deployment
        return None


class StubEvaluationFrameworkClient:
    def __init__(self, *, scores: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[dict] = []
        self._scores = scores if scores is not None else []

    async def list_scores(self, *, tenant_id: str, agent_ref: str) -> list[dict[str, Any]]:
        self.calls.append({"tenant_id": tenant_id, "agent_ref": agent_ref})
        return self._scores


__all__ = ["InMemoryLLMOpsRepository", "StubEvaluationFrameworkClient"]
