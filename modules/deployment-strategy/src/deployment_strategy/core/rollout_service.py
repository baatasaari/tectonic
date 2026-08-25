"""Rollout Service (LLD §2 sub-components, §Level 3 "The rollout state
machine"): deploy / promote / rollback, plus the active-deployment
query. `promote` always re-runs the canary health check -- it never
trusts an earlier verdict -- and superseding the previous active
deployment for the same target is automatic, not a separate manual
step.
"""
from __future__ import annotations

from deployment_strategy.core.canary_health_calculator import CanaryHealthCalculator
from deployment_strategy.core.domain import (
    CanaryHealthCheckFailedError,
    CanaryHealthResult,
    DeploymentNotFoundError,
    DeploymentRecord,
    DeploymentStage,
    InvalidTransitionError,
    NoActiveDeploymentError,
    is_legal_transition,
    new_id,
    now,
)
from deployment_strategy.core.ports import DeploymentStrategyRepository


class RolloutService:
    def __init__(self, repository: DeploymentStrategyRepository, canary_health: CanaryHealthCalculator) -> None:
        self._repository = repository
        self._canary_health = canary_health

    async def deploy(
        self, *, tenant_id: str, service_name: str, build_ref: str, target: str,
        canary_percentage: int = 10, budget_policy_id: str | None = None,
    ) -> DeploymentRecord:
        return await self._repository.create_deployment(
            DeploymentRecord(
                id=new_id(), tenant_id=tenant_id, service_name=service_name, build_ref=build_ref, target=target,
                canary_percentage=canary_percentage, budget_policy_id=budget_policy_id,
            )
        )

    async def _get_deployment(self, deployment_id: str) -> DeploymentRecord:
        record = await self._repository.get_deployment(deployment_id)
        if record is None:
            raise DeploymentNotFoundError(deployment_id)
        return record

    async def canary_health(self, deployment_id: str) -> CanaryHealthResult:
        deployment = await self._get_deployment(deployment_id)
        return await self._canary_health.evaluate(deployment)

    async def promote(self, deployment_id: str) -> DeploymentRecord:
        deployment = await self._get_deployment(deployment_id)
        if not is_legal_transition(deployment.stage, DeploymentStage.ACTIVE):
            raise InvalidTransitionError(deployment.stage, DeploymentStage.ACTIVE)

        health_result = await self._canary_health.evaluate(deployment)
        if not health_result.passed:
            raise CanaryHealthCheckFailedError(health_result.reason)

        previous_active = await self._repository.get_active_deployment(
            tenant_id=deployment.tenant_id, service_name=deployment.service_name, target=deployment.target,
        )
        if previous_active is not None and previous_active.id != deployment.id:
            previous_active.stage = DeploymentStage.SUPERSEDED
            previous_active.updated_at = now()
            await self._repository.update_deployment(previous_active)

        deployment.stage = DeploymentStage.ACTIVE
        deployment.promoted_at = now()
        deployment.updated_at = now()
        await self._repository.update_deployment(deployment)
        return deployment

    async def rollback(self, deployment_id: str, *, reason: str) -> DeploymentRecord:
        deployment = await self._get_deployment(deployment_id)
        if not is_legal_transition(deployment.stage, DeploymentStage.ROLLED_BACK):
            raise InvalidTransitionError(deployment.stage, DeploymentStage.ROLLED_BACK)

        deployment.stage = DeploymentStage.ROLLED_BACK
        deployment.rolled_back_at = now()
        deployment.rollback_reason = reason
        deployment.updated_at = now()
        await self._repository.update_deployment(deployment)
        return deployment

    async def get_active_deployment(self, *, tenant_id: str, service_name: str, target: str) -> DeploymentRecord:
        deployment = await self._repository.get_active_deployment(
            tenant_id=tenant_id, service_name=service_name, target=target,
        )
        if deployment is None:
            raise NoActiveDeploymentError(service_name, target)
        return deployment
