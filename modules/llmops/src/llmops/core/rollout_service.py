"""Rollout Service (LLD §2 sub-components, §Level 3 "The rollout state
machine"): start_canary / promote / rollback, plus the active-version
query. `promote` always re-runs the canary gate -- it never trusts an
earlier pass -- and superseding the previous active deployment for the
same target is automatic, not a separate manual step.

`promote` additionally blocks on Evaluation Framework's own `POST /gate`
verdict for the model version's most recent eval run -- the
evaluation-gated release path, distinct from (and checked in addition
to) the canary pass-rate-over-time comparison above: a version whose
canary traffic looks fine on aggregate pass rate can still have a
failing most-recent evaluation run Evaluation Framework itself flags as
blocking (see PromptOps' own `ABTestingService.conclude` for the
identical pattern applied to prompt-version promotion).
"""
from __future__ import annotations

from llmops.core.canary_evaluation_service import CanaryEvaluationService, evaluation_ref
from llmops.core.domain import (
    CanaryGateFailedError,
    CanaryGateResult,
    DeploymentNotFoundError,
    DeploymentRecord,
    DeploymentStage,
    InvalidTransitionError,
    ModelVersionNotFoundError,
    ModelVersionRecord,
    ModelVersionStatus,
    NoActiveVersionError,
    is_legal_transition,
    new_id,
    now,
)
from llmops.core.ports import EvaluationFrameworkClient, LLMOpsRepository


class RolloutService:
    def __init__(
        self, repository: LLMOpsRepository, canary_evaluation: CanaryEvaluationService,
        evaluation_framework: EvaluationFrameworkClient,
    ) -> None:
        self._repository = repository
        self._canary_evaluation = canary_evaluation
        self._evaluation_framework = evaluation_framework

    async def start_canary(
        self, *, tenant_id: str, model_version_id: str, target: str, canary_percentage: int = 10,
    ) -> DeploymentRecord:
        model_version = await self._repository.get_model_version(model_version_id)
        if model_version is None:
            raise ModelVersionNotFoundError(model_version_id)

        deployment = await self._repository.create_deployment(
            DeploymentRecord(
                id=new_id(), tenant_id=tenant_id, model_version_id=model_version_id, model_name=model_version.model_name,
                target=target, canary_percentage=canary_percentage,
            )
        )

        model_version.status = ModelVersionStatus.CANARY
        await self._repository.update_model_version(model_version)
        return deployment

    async def _get_deployment(self, deployment_id: str) -> DeploymentRecord:
        record = await self._repository.get_deployment(deployment_id)
        if record is None:
            raise DeploymentNotFoundError(deployment_id)
        return record

    async def canary_gate(self, deployment_id: str) -> CanaryGateResult:
        deployment = await self._get_deployment(deployment_id)
        model_version = await self._repository.get_model_version(deployment.model_version_id)
        if model_version is None:
            raise ModelVersionNotFoundError(deployment.model_version_id)
        return await self._canary_evaluation.evaluate(model_version)

    async def promote(self, deployment_id: str) -> DeploymentRecord:
        deployment = await self._get_deployment(deployment_id)
        if not is_legal_transition(deployment.stage, DeploymentStage.ACTIVE):
            raise InvalidTransitionError(deployment.stage, DeploymentStage.ACTIVE)

        model_version = await self._repository.get_model_version(deployment.model_version_id)
        if model_version is None:
            raise ModelVersionNotFoundError(deployment.model_version_id)

        gate_result = await self._canary_evaluation.evaluate(model_version)
        if not gate_result.passed:
            raise CanaryGateFailedError(gate_result.reason)

        eval_gate = await self._evaluation_framework.gate_latest_run(
            tenant_id=model_version.tenant_id, agent_ref=evaluation_ref(model_version),
        )
        if eval_gate is not None and not eval_gate.get("overall_passed", True):
            blocking = ", ".join(eval_gate.get("blocking_failures", []))
            raise CanaryGateFailedError(f"evaluation_gate_failed: {blocking}")

        previous_active = await self._repository.get_active_deployment(
            tenant_id=deployment.tenant_id, model_name=deployment.model_name, target=deployment.target,
        )
        if previous_active is not None and previous_active.id != deployment.id:
            previous_active.stage = DeploymentStage.SUPERSEDED
            previous_active.updated_at = now()
            await self._repository.update_deployment(previous_active)
            previous_version = await self._repository.get_model_version(previous_active.model_version_id)
            if previous_version is not None:
                previous_version.status = ModelVersionStatus.SUPERSEDED
                await self._repository.update_model_version(previous_version)

        deployment.stage = DeploymentStage.ACTIVE
        deployment.promoted_at = now()
        deployment.updated_at = now()
        await self._repository.update_deployment(deployment)

        model_version.status = ModelVersionStatus.ACTIVE
        await self._repository.update_model_version(model_version)
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

        model_version = await self._repository.get_model_version(deployment.model_version_id)
        if model_version is not None:
            model_version.status = ModelVersionStatus.ROLLED_BACK
            await self._repository.update_model_version(model_version)
        return deployment

    async def get_active_version(self, *, tenant_id: str, model_name: str, target: str) -> ModelVersionRecord:
        deployment = await self._repository.get_active_deployment(tenant_id=tenant_id, model_name=model_name, target=target)
        if deployment is None:
            raise NoActiveVersionError(model_name, target)
        model_version = await self._repository.get_model_version(deployment.model_version_id)
        if model_version is None:
            raise NoActiveVersionError(model_name, target)
        return model_version
