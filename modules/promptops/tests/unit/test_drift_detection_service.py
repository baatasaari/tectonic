"""Tests for core/drift_detection_service.py -- reuses the same
two-proportion z-test to compare a version's current pass rate against
its pass rate at promotion time."""
from __future__ import annotations

import pytest

from promptops.core.ab_testing_service import evaluation_ref
from promptops.core.domain import PromptVersionNotFoundError
from promptops.core.fakes import StubEvaluationFrameworkClient


async def test_check_raises_when_missing(harness):
    with pytest.raises(PromptVersionNotFoundError):
        await harness.drift_detection_service.check("does-not-exist")


async def test_check_has_no_baseline_for_a_never_promoted_version(harness):
    version = await harness.prompt_registry_service.register(
        tenant_id="acme", prompt_name="p", version="1", template="t",
    )

    result = await harness.drift_detection_service.check(version.id)

    assert result.drifted is False
    assert "no baseline" in result.reason


async def test_check_is_insufficient_data_with_no_current_history(harness_factory):
    h = harness_factory(evaluation_framework=StubEvaluationFrameworkClient(scores=[]))
    version = await h.prompt_registry_service.register(tenant_id="acme", prompt_name="p", version="1", template="t")
    version.promoted_pass_rate = 0.95
    version.promoted_sample_size = 20
    await h.repository.update_prompt_version(version)

    result = await h.drift_detection_service.check(version.id)

    assert result.drifted is False
    assert "insufficient_data" in result.reason


async def test_check_detects_a_significant_drop(harness_factory):
    ref = evaluation_ref("p", "1")
    current_scores = [{"passed": False}] * 18 + [{"passed": True}] * 2  # pass rate 0.1, was 0.95
    h = harness_factory(evaluation_framework=StubEvaluationFrameworkClient(scores_by_ref={ref: current_scores}))
    version = await h.prompt_registry_service.register(tenant_id="acme", prompt_name="p", version="1", template="t")
    version.promoted_pass_rate = 0.95
    version.promoted_sample_size = 20
    await h.repository.update_prompt_version(version)

    result = await h.drift_detection_service.check(version.id)

    assert result.drifted is True
    assert result.current_pass_rate == 0.1


async def test_check_does_not_flag_an_improvement_as_drift(harness_factory):
    ref = evaluation_ref("p", "1")
    current_scores = [{"passed": True}] * 20  # pass rate 1.0, was 0.5 -- an improvement
    h = harness_factory(evaluation_framework=StubEvaluationFrameworkClient(scores_by_ref={ref: current_scores}))
    version = await h.prompt_registry_service.register(tenant_id="acme", prompt_name="p", version="1", template="t")
    version.promoted_pass_rate = 0.5
    version.promoted_sample_size = 20
    await h.repository.update_prompt_version(version)

    result = await h.drift_detection_service.check(version.id)

    assert result.drifted is False


async def test_check_does_not_flag_a_stable_pass_rate_as_drift(harness_factory):
    ref = evaluation_ref("p", "1")
    current_scores = [{"passed": True}] * 19 + [{"passed": False}] * 1  # pass rate 0.95, same as baseline
    h = harness_factory(evaluation_framework=StubEvaluationFrameworkClient(scores_by_ref={ref: current_scores}))
    version = await h.prompt_registry_service.register(tenant_id="acme", prompt_name="p", version="1", template="t")
    version.promoted_pass_rate = 0.95
    version.promoted_sample_size = 20
    await h.repository.update_prompt_version(version)

    result = await h.drift_detection_service.check(version.id)

    assert result.drifted is False
