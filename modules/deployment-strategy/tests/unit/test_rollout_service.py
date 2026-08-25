"""Tests for core/rollout_service.py -- deploy/promote/rollback and the
legal-transition state machine, plus auto-superseding the previous
active deployment for the same target."""
from __future__ import annotations

import pytest

from deployment_strategy.core.domain import (
    CanaryHealthCheckFailedError,
    DeploymentStage,
    InvalidTransitionError,
    NoActiveDeploymentError,
)
from deployment_strategy.core.fakes import StubEvaluationFrameworkClient

_PASSING_SCORES = [{"passed": True}] * 5


async def test_deploy_starts_in_canary_stage(harness):
    deployment = await harness.rollout_service.deploy(
        tenant_id="acme", service_name="conversational-engine", build_ref="v1", target="prod",
    )

    assert deployment.stage == DeploymentStage.CANARY
    assert deployment.canary_percentage == 10


async def test_promote_fails_when_health_check_is_insufficient_data(harness_factory):
    h = harness_factory(evaluation_framework=StubEvaluationFrameworkClient(scores=[]))
    deployment = await h.rollout_service.deploy(
        tenant_id="acme", service_name="svc", build_ref="v1", target="prod",
    )

    with pytest.raises(CanaryHealthCheckFailedError):
        await h.rollout_service.promote(deployment.id)


async def test_full_deploy_promote_active_flow(harness_factory):
    h = harness_factory(
        evaluation_framework=StubEvaluationFrameworkClient(scores=_PASSING_SCORES), min_groundedness_sample_size=3,
    )
    deployment = await h.rollout_service.deploy(
        tenant_id="acme", service_name="svc", build_ref="v1", target="prod",
    )

    promoted = await h.rollout_service.promote(deployment.id)
    assert promoted.stage == DeploymentStage.ACTIVE
    assert promoted.promoted_at is not None

    active = await h.rollout_service.get_active_deployment(tenant_id="acme", service_name="svc", target="prod")
    assert active.id == deployment.id


async def test_promoting_a_new_deployment_supersedes_the_previous_active_one(harness_factory):
    h = harness_factory(
        evaluation_framework=StubEvaluationFrameworkClient(scores=_PASSING_SCORES), min_groundedness_sample_size=3,
    )
    d1 = await h.rollout_service.deploy(tenant_id="acme", service_name="svc", build_ref="v1", target="prod")
    await h.rollout_service.promote(d1.id)

    d2 = await h.rollout_service.deploy(tenant_id="acme", service_name="svc", build_ref="v2", target="prod")
    await h.rollout_service.promote(d2.id)

    refetched_d1 = await h.repository.get_deployment(d1.id)
    assert refetched_d1.stage == DeploymentStage.SUPERSEDED

    active = await h.rollout_service.get_active_deployment(tenant_id="acme", service_name="svc", target="prod")
    assert active.id == d2.id


async def test_rollback_requires_a_reason_and_records_it(harness):
    deployment = await harness.rollout_service.deploy(
        tenant_id="acme", service_name="svc", build_ref="v1", target="prod",
    )

    rolled_back = await harness.rollout_service.rollback(deployment.id, reason="regression in prod")

    assert rolled_back.stage == DeploymentStage.ROLLED_BACK
    assert rolled_back.rollback_reason == "regression in prod"
    assert rolled_back.rolled_back_at is not None


async def test_rollback_on_an_already_rolled_back_deployment_is_illegal(harness):
    deployment = await harness.rollout_service.deploy(
        tenant_id="acme", service_name="svc", build_ref="v1", target="prod",
    )
    await harness.rollout_service.rollback(deployment.id, reason="first")

    with pytest.raises(InvalidTransitionError):
        await harness.rollout_service.rollback(deployment.id, reason="second")


async def test_promote_on_a_rolled_back_deployment_is_illegal(harness_factory):
    h = harness_factory(evaluation_framework=StubEvaluationFrameworkClient(scores=_PASSING_SCORES))
    deployment = await h.rollout_service.deploy(tenant_id="acme", service_name="svc", build_ref="v1", target="prod")
    await h.rollout_service.rollback(deployment.id, reason="bad build")

    with pytest.raises(InvalidTransitionError):
        await h.rollout_service.promote(deployment.id)


async def test_get_active_deployment_raises_when_nothing_is_active(harness):
    with pytest.raises(NoActiveDeploymentError):
        await harness.rollout_service.get_active_deployment(tenant_id="acme", service_name="svc", target="prod")


async def test_active_deployments_are_scoped_by_target(harness_factory):
    h = harness_factory(
        evaluation_framework=StubEvaluationFrameworkClient(scores=_PASSING_SCORES), min_groundedness_sample_size=3,
    )
    prod = await h.rollout_service.deploy(tenant_id="acme", service_name="svc", build_ref="v1", target="prod")
    await h.rollout_service.promote(prod.id)

    with pytest.raises(NoActiveDeploymentError):
        await h.rollout_service.get_active_deployment(tenant_id="acme", service_name="svc", target="staging")
