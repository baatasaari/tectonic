"""In-memory fakes for unit tests (LLD "Deployability and testability
contract")."""
from __future__ import annotations

from typing import Any

from deployment_strategy.core.domain import DeploymentRecord, DeploymentStage

_UNSET = object()


class InMemoryDeploymentStrategyRepository:
    def __init__(self) -> None:
        self.deployments: dict[str, DeploymentRecord] = {}

    async def create_deployment(self, record: DeploymentRecord) -> DeploymentRecord:
        self.deployments[record.id] = record
        return record

    async def get_deployment(self, deployment_id: str) -> DeploymentRecord | None:
        return self.deployments.get(deployment_id)

    async def update_deployment(self, record: DeploymentRecord) -> DeploymentRecord:
        self.deployments[record.id] = record
        return record

    async def get_active_deployment(self, *, tenant_id: str, service_name: str, target: str) -> DeploymentRecord | None:
        for deployment in self.deployments.values():
            if (
                deployment.tenant_id == tenant_id and deployment.service_name == service_name
                and deployment.target == target and deployment.stage == DeploymentStage.ACTIVE
            ):
                return deployment
        return None

    async def list_deployments(
        self, *, tenant_id: str | None = None, service_name: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[DeploymentRecord], int]:
        results = list(self.deployments.values())
        if tenant_id is not None:
            results = [d for d in results if d.tenant_id == tenant_id]
        if service_name is not None:
            results = [d for d in results if d.service_name == service_name]
        results = sorted(results, key=lambda d: d.created_at)
        return results[offset:offset + limit], len(results)


class StubEvaluationFrameworkClient:
    def __init__(self, *, scores: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[dict] = []
        self._scores = scores if scores is not None else []

    async def list_scores(self, *, tenant_id: str, agent_ref: str) -> list[dict[str, Any]]:
        self.calls.append({"tenant_id": tenant_id, "agent_ref": agent_ref})
        return self._scores


class StubFinOpsClient:
    def __init__(self, *, utilisation_ratio: float | None | object = _UNSET) -> None:
        self.calls: list[dict] = []
        self._utilisation_ratio = None if utilisation_ratio is _UNSET else utilisation_ratio

    async def cost_report_utilisation(self, *, tenant_id: str, period: str, budget_policy_id: str) -> float | None:
        self.calls.append({"tenant_id": tenant_id, "period": period, "budget_policy_id": budget_policy_id})
        return self._utilisation_ratio


__all__ = ["InMemoryDeploymentStrategyRepository", "StubEvaluationFrameworkClient", "StubFinOpsClient"]
