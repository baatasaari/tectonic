"""Abstract ports this module depends on: persistence, and the real
Evaluation Framework peer client the Canary Evaluation Service reads
from.
"""
from __future__ import annotations

from typing import Any, Protocol

from llmops.core.domain import DeploymentRecord, ModelVersionRecord


class LLMOpsRepository(Protocol):
    async def create_model_version(self, record: ModelVersionRecord) -> ModelVersionRecord: ...

    async def get_model_version(self, model_version_id: str) -> ModelVersionRecord | None: ...

    async def update_model_version(self, record: ModelVersionRecord) -> ModelVersionRecord: ...

    async def list_model_versions(
        self, *, tenant_id: str | None = None, model_name: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ModelVersionRecord], int]: ...

    async def create_deployment(self, record: DeploymentRecord) -> DeploymentRecord: ...

    async def get_deployment(self, deployment_id: str) -> DeploymentRecord | None: ...

    async def update_deployment(self, record: DeploymentRecord) -> DeploymentRecord: ...

    async def get_active_deployment(
        self, *, tenant_id: str, model_name: str, target: str,
    ) -> DeploymentRecord | None:
        """The current `active`-stage deployment for this (tenant, model_name,
        target), or None if nothing is active there yet."""
        ...


class EvaluationFrameworkClient(Protocol):
    async def list_scores(self, *, tenant_id: str, agent_ref: str) -> list[dict[str, Any]]:
        """Each item at least `{"score": float, "threshold": float,
        "passed": bool}`, per Evaluation Framework's own MetricScoreSchema.
        Empty list, not an error, when the version has no evaluation
        history yet."""
        ...
