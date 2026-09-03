"""Tests for core/rollout_service.py -- start_canary/promote/rollback,
supersession, the active-version query, and the illegal-transition
matrix."""
from __future__ import annotations

import pytest

from llmops.core.domain import (
    CanaryGateFailedError,
    DeploymentStage,
    InvalidTransitionError,
    ModelVersionNotFoundError,
    ModelVersionStatus,
    NoActiveVersionError,
)
from llmops.core.fakes import StubEvaluationFrameworkClient

_PASSING_SCORES = [{"passed": True}] * 5


async def test_start_canary_raises_for_an_unknown_model_version(harness):
    with pytest.raises(ModelVersionNotFoundError):
        await harness.rollout_service.start_canary(tenant_id="acme", model_version_id="does-not-exist", target="prod")


async def test_start_canary_creates_a_canary_deployment_and_marks_the_version_canary(harness):
    version = await harness.model_registry_service.register(
        tenant_id="acme", model_name="chat-default", version="1", artifact_ref="openai/gpt-x",
    )

    deployment = await harness.rollout_service.start_canary(
        tenant_id="acme", model_version_id=version.id, target="prod", canary_percentage=20,
    )

    assert deployment.stage == DeploymentStage.CANARY
    assert deployment.canary_percentage == 20
    persisted_version = await harness.repository.get_model_version(version.id)
    assert persisted_version.status == ModelVersionStatus.CANARY


async def test_promote_fails_with_the_gates_own_reason_when_the_gate_does_not_pass(harness_factory):
    evalfw = StubEvaluationFrameworkClient(scores=[])
    harness = harness_factory(evaluation_framework=evalfw)
    version = await harness.model_registry_service.register(tenant_id="acme", model_name="m", version="1", artifact_ref="a")
    deployment = await harness.rollout_service.start_canary(tenant_id="acme", model_version_id=version.id, target="prod")

    with pytest.raises(CanaryGateFailedError) as exc_info:
        await harness.rollout_service.promote(deployment.id)
    assert "insufficient_data" in exc_info.value.reason

    # A failed promote must not have moved the deployment out of canary.
    persisted = await harness.repository.get_deployment(deployment.id)
    assert persisted.stage == DeploymentStage.CANARY


async def test_promote_succeeds_when_the_gate_passes(harness_factory):
    evalfw = StubEvaluationFrameworkClient(scores=_PASSING_SCORES)
    harness = harness_factory(evaluation_framework=evalfw)
    version = await harness.model_registry_service.register(tenant_id="acme", model_name="m", version="1", artifact_ref="a")
    deployment = await harness.rollout_service.start_canary(tenant_id="acme", model_version_id=version.id, target="prod")

    promoted = await harness.rollout_service.promote(deployment.id)

    assert promoted.stage == DeploymentStage.ACTIVE
    assert promoted.promoted_at is not None
    persisted_version = await harness.repository.get_model_version(version.id)
    assert persisted_version.status == ModelVersionStatus.ACTIVE


async def test_promote_blocks_when_evaluation_framework_gate_fails(harness_factory):
    """A version whose canary traffic passed the local pass-rate gate can
    still have a failing most recent evaluation run -- Evaluation
    Framework's own `/gate` is the platform's single source of truth for
    that, so `promote` must not promote around it."""
    evalfw = StubEvaluationFrameworkClient(
        scores=_PASSING_SCORES, gate_result={"overall_passed": False, "blocking_failures": ["faithfulness"]},
    )
    harness = harness_factory(evaluation_framework=evalfw)
    version = await harness.model_registry_service.register(tenant_id="acme", model_name="m", version="1", artifact_ref="a")
    deployment = await harness.rollout_service.start_canary(tenant_id="acme", model_version_id=version.id, target="prod")

    with pytest.raises(CanaryGateFailedError) as exc_info:
        await harness.rollout_service.promote(deployment.id)
    assert "faithfulness" in exc_info.value.reason

    persisted = await harness.repository.get_deployment(deployment.id)
    assert persisted.stage == DeploymentStage.CANARY


async def test_promote_succeeds_when_evaluation_framework_gate_passes(harness_factory):
    evalfw = StubEvaluationFrameworkClient(
        scores=_PASSING_SCORES, gate_result={"overall_passed": True, "blocking_failures": []},
    )
    harness = harness_factory(evaluation_framework=evalfw)
    version = await harness.model_registry_service.register(tenant_id="acme", model_name="m", version="1", artifact_ref="a")
    deployment = await harness.rollout_service.start_canary(tenant_id="acme", model_version_id=version.id, target="prod")

    promoted = await harness.rollout_service.promote(deployment.id)

    assert promoted.stage == DeploymentStage.ACTIVE
    assert evalfw.gate_calls


async def test_promote_succeeds_when_no_eval_run_exists_yet(harness_factory):
    """`gate_latest_run` returning `None` (no eval run yet) must not block
    promotion -- the same "no history is not a failure" convention
    `list_scores` already establishes, not a new, stricter one."""
    evalfw = StubEvaluationFrameworkClient(scores=_PASSING_SCORES)
    harness = harness_factory(evaluation_framework=evalfw)
    version = await harness.model_registry_service.register(tenant_id="acme", model_name="m", version="1", artifact_ref="a")
    deployment = await harness.rollout_service.start_canary(tenant_id="acme", model_version_id=version.id, target="prod")

    promoted = await harness.rollout_service.promote(deployment.id)

    assert promoted.stage == DeploymentStage.ACTIVE


async def test_promoting_a_new_version_supersedes_the_previously_active_one(harness_factory):
    evalfw = StubEvaluationFrameworkClient(scores=_PASSING_SCORES)
    harness = harness_factory(evaluation_framework=evalfw)
    v1 = await harness.model_registry_service.register(tenant_id="acme", model_name="m", version="1", artifact_ref="a")
    d1 = await harness.rollout_service.start_canary(tenant_id="acme", model_version_id=v1.id, target="prod")
    await harness.rollout_service.promote(d1.id)

    v2 = await harness.model_registry_service.register(tenant_id="acme", model_name="m", version="2", artifact_ref="b")
    d2 = await harness.rollout_service.start_canary(tenant_id="acme", model_version_id=v2.id, target="prod")
    await harness.rollout_service.promote(d2.id)

    superseded_d1 = await harness.repository.get_deployment(d1.id)
    superseded_v1 = await harness.repository.get_model_version(v1.id)
    assert superseded_d1.stage == DeploymentStage.SUPERSEDED
    assert superseded_v1.status == ModelVersionStatus.SUPERSEDED

    active_version = await harness.rollout_service.get_active_version(tenant_id="acme", model_name="m", target="prod")
    assert active_version.id == v2.id


async def test_rollback_from_canary(harness):
    version = await harness.model_registry_service.register(tenant_id="acme", model_name="m", version="1", artifact_ref="a")
    deployment = await harness.rollout_service.start_canary(tenant_id="acme", model_version_id=version.id, target="prod")

    rolled_back = await harness.rollout_service.rollback(deployment.id, reason="latency regression")

    assert rolled_back.stage == DeploymentStage.ROLLED_BACK
    assert rolled_back.rollback_reason == "latency regression"


async def test_rollback_from_active(harness_factory):
    evalfw = StubEvaluationFrameworkClient(scores=_PASSING_SCORES)
    harness = harness_factory(evaluation_framework=evalfw)
    version = await harness.model_registry_service.register(tenant_id="acme", model_name="m", version="1", artifact_ref="a")
    deployment = await harness.rollout_service.start_canary(tenant_id="acme", model_version_id=version.id, target="prod")
    await harness.rollout_service.promote(deployment.id)

    rolled_back = await harness.rollout_service.rollback(deployment.id, reason="post-promotion regression")

    assert rolled_back.stage == DeploymentStage.ROLLED_BACK


async def test_rolling_back_an_already_rolled_back_deployment_is_illegal(harness):
    version = await harness.model_registry_service.register(tenant_id="acme", model_name="m", version="1", artifact_ref="a")
    deployment = await harness.rollout_service.start_canary(tenant_id="acme", model_version_id=version.id, target="prod")
    await harness.rollout_service.rollback(deployment.id, reason="first")

    with pytest.raises(InvalidTransitionError):
        await harness.rollout_service.rollback(deployment.id, reason="second")


async def test_promoting_an_already_active_deployment_is_illegal(harness_factory):
    evalfw = StubEvaluationFrameworkClient(scores=_PASSING_SCORES)
    harness = harness_factory(evaluation_framework=evalfw)
    version = await harness.model_registry_service.register(tenant_id="acme", model_name="m", version="1", artifact_ref="a")
    deployment = await harness.rollout_service.start_canary(tenant_id="acme", model_version_id=version.id, target="prod")
    await harness.rollout_service.promote(deployment.id)

    with pytest.raises(InvalidTransitionError):
        await harness.rollout_service.promote(deployment.id)


async def test_get_active_version_raises_when_nothing_is_active(harness):
    with pytest.raises(NoActiveVersionError):
        await harness.rollout_service.get_active_version(tenant_id="acme", model_name="m", target="prod")
