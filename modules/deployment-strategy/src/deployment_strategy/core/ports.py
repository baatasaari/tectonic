"""Abstract ports this module depends on: persistence, and the two real
platform-peer clients the Canary Health Calculator reads from.
"""
from __future__ import annotations

from typing import Any, Protocol

from deployment_strategy.core.domain import DeploymentRecord


class DeploymentStrategyRepository(Protocol):
    async def create_deployment(self, record: DeploymentRecord) -> DeploymentRecord: ...

    async def get_deployment(self, deployment_id: str) -> DeploymentRecord | None: ...

    async def update_deployment(self, record: DeploymentRecord) -> DeploymentRecord: ...

    async def get_active_deployment(
        self, *, tenant_id: str, service_name: str, target: str,
    ) -> DeploymentRecord | None:
        """The current `active`-stage deployment for this (tenant, service_name,
        target), or None if nothing is active there yet."""
        ...

    async def list_deployments(
        self, *, tenant_id: str | None = None, service_name: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[DeploymentRecord], int]: ...


class EvaluationFrameworkClient(Protocol):
    async def list_scores(self, *, tenant_id: str, agent_ref: str) -> list[dict[str, Any]]:
        """Each item at least `{"score": float, "threshold": float,
        "passed": bool}`, per Evaluation Framework's own MetricScoreSchema.
        Empty list, not an error, when the deployment has no evaluation
        history yet."""
        ...


class FinOpsClient(Protocol):
    async def cost_report_utilisation(self, *, tenant_id: str, period: str, budget_policy_id: str) -> float | None:
        """The `utilisation_ratio` from FinOps's own `GET
        /cost-reports/{tenant_id}`, or `None` if that budget policy
        doesn't exist (e.g. a stale/mistyped `budget_policy_id`) --
        "not configured", not an error."""
        ...
