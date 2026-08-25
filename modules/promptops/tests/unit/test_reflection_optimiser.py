"""Tests for core/reflection_optimiser.py -- the one bounded autonomous
action this module takes: proposing a new draft version from a real
failing-metric summary, never auto-deploying it."""
from __future__ import annotations

import pytest

from promptops.core.ab_testing_service import evaluation_ref
from promptops.core.domain import PromptVersionNotFoundError, PromptVersionStatus
from promptops.core.fakes import StubEvaluationFrameworkClient, StubLLMGatewayClient

_FAILING_SCORES = [
    {"metric_name": "groundedness", "score": 0.4, "threshold": 0.8, "passed": False},
    {"metric_name": "groundedness", "score": 0.3, "threshold": 0.8, "passed": False},
    {"metric_name": "groundedness", "score": 0.9, "threshold": 0.8, "passed": True},
]
_PASSING_SCORES = [{"metric_name": "groundedness", "score": 0.95, "threshold": 0.8, "passed": True}] * 5


async def test_propose_raises_when_version_missing(harness):
    with pytest.raises(PromptVersionNotFoundError):
        await harness.reflection_optimiser.propose("does-not-exist")


async def test_propose_declines_with_insufficient_evidence(harness_factory):
    h = harness_factory(evaluation_framework=StubEvaluationFrameworkClient(scores=[]), min_reflection_sample_size=3)
    version = await h.prompt_registry_service.register(tenant_id="acme", prompt_name="p", version="1", template="t")

    result = await h.reflection_optimiser.propose(version.id)

    assert result is None
    assert h.llm_gateway.calls == []


async def test_propose_declines_when_pass_rate_is_already_high(harness_factory):
    ref = evaluation_ref("p", "1")
    evalfw = StubEvaluationFrameworkClient(scores_by_ref={ref: _PASSING_SCORES})
    h = harness_factory(evaluation_framework=evalfw, min_reflection_sample_size=3, max_pass_rate_before_reflection=0.9)
    version = await h.prompt_registry_service.register(tenant_id="acme", prompt_name="p", version="1", template="t")

    result = await h.reflection_optimiser.propose(version.id)

    assert result is None
    assert h.llm_gateway.calls == []


async def test_propose_generates_a_new_draft_version_from_failing_metrics(harness_factory):
    ref = evaluation_ref("p", "1")
    evalfw = StubEvaluationFrameworkClient(scores_by_ref={ref: _FAILING_SCORES})
    llm_gateway = StubLLMGatewayClient(response="An improved, more grounded template.")
    h = harness_factory(
        evaluation_framework=evalfw, llm_gateway=llm_gateway, min_reflection_sample_size=3,
        max_pass_rate_before_reflection=0.9,
    )
    version = await h.prompt_registry_service.register(
        tenant_id="acme", prompt_name="p", version="1", template="Original template.",
    )

    new_version = await h.reflection_optimiser.propose(version.id)

    assert new_version is not None
    assert new_version.status == PromptVersionStatus.DRAFT
    assert new_version.parent_version_id == version.id
    assert new_version.template == "An improved, more grounded template."
    assert new_version.id != version.id

    assert len(llm_gateway.calls) == 1
    prompt_sent = llm_gateway.calls[0]["prompt"]
    assert "groundedness" in prompt_sent
    assert "Original template." in prompt_sent


async def test_propose_never_mutates_the_original_version(harness_factory):
    ref = evaluation_ref("p", "1")
    evalfw = StubEvaluationFrameworkClient(scores_by_ref={ref: _FAILING_SCORES})
    h = harness_factory(evaluation_framework=evalfw, min_reflection_sample_size=3)
    version = await h.prompt_registry_service.register(tenant_id="acme", prompt_name="p", version="1", template="t")

    await h.reflection_optimiser.propose(version.id)

    refetched = await h.repository.get_prompt_version(version.id)
    assert refetched.status == PromptVersionStatus.DRAFT
    assert refetched.template == "t"
