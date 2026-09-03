"""Tests for core/ab_testing_service.py -- the real two-proportion
z-test gate between two prompt versions' evaluation histories."""
from __future__ import annotations

import pytest

from promptops.core.ab_testing_service import evaluation_ref
from promptops.core.domain import (
    ABTestNotConclusiveError,
    EvaluationGateFailedError,
    InvalidTransitionError,
    PromptVersionStatus,
)
from promptops.core.fakes import StubEvaluationFrameworkClient

_PASSING = [{"passed": True}] * 20
_FAILING = [{"passed": False}] * 20


async def _register_two_versions(harness):
    a = await harness.prompt_registry_service.register(
        tenant_id="acme", prompt_name="claims-summariser", version="1", template="template a",
    )
    b = await harness.prompt_registry_service.register(
        tenant_id="acme", prompt_name="claims-summariser", version="2", template="template b",
    )
    return a, b


async def test_start_transitions_both_versions_to_testing(harness):
    a, b = await _register_two_versions(harness)

    ab_test = await harness.ab_testing_service.start(
        tenant_id="acme", prompt_name="claims-summariser", version_a_id=a.id, version_b_id=b.id,
    )

    refetched_a = await harness.repository.get_prompt_version(a.id)
    refetched_b = await harness.repository.get_prompt_version(b.id)
    assert refetched_a.status == PromptVersionStatus.TESTING
    assert refetched_b.status == PromptVersionStatus.TESTING
    assert ab_test.version_a_id == a.id


async def test_start_on_an_already_testing_version_is_illegal(harness):
    a, b = await _register_two_versions(harness)
    await harness.ab_testing_service.start(
        tenant_id="acme", prompt_name="claims-summariser", version_a_id=a.id, version_b_id=b.id,
    )
    c = await harness.prompt_registry_service.register(
        tenant_id="acme", prompt_name="claims-summariser", version="3", template="template c",
    )

    with pytest.raises(InvalidTransitionError):
        await harness.ab_testing_service.start(
            tenant_id="acme", prompt_name="claims-summariser", version_a_id=a.id, version_b_id=c.id,
        )


async def test_evaluate_is_insufficient_data_below_min_sample_size(harness_factory):
    h = harness_factory(evaluation_framework=StubEvaluationFrameworkClient(scores=[]), min_sample_size_per_arm=3)
    a, b = await _register_two_versions(h)
    ab_test = await h.ab_testing_service.start(
        tenant_id="acme", prompt_name="claims-summariser", version_a_id=a.id, version_b_id=b.id,
    )

    result = await h.ab_testing_service.evaluate(ab_test.id)

    assert result.significant is False
    assert result.winner_version_id is None
    assert "insufficient_data" in result.reason


async def test_evaluate_finds_a_significant_winner(harness_factory):
    a_ref = evaluation_ref("claims-summariser", "1")
    b_ref = evaluation_ref("claims-summariser", "2")
    evalfw = StubEvaluationFrameworkClient(scores_by_ref={a_ref: _PASSING, b_ref: _FAILING})
    h = harness_factory(evaluation_framework=evalfw, min_sample_size_per_arm=3)
    a, b = await _register_two_versions(h)
    ab_test = await h.ab_testing_service.start(
        tenant_id="acme", prompt_name="claims-summariser", version_a_id=a.id, version_b_id=b.id,
    )

    result = await h.ab_testing_service.evaluate(ab_test.id)

    assert result.significant is True
    assert result.winner_version_id == a.id


async def test_conclude_raises_when_not_significant(harness_factory):
    a_ref = evaluation_ref("claims-summariser", "1")
    b_ref = evaluation_ref("claims-summariser", "2")
    same_scores = [{"passed": True}] * 6 + [{"passed": False}] * 4
    evalfw = StubEvaluationFrameworkClient(scores_by_ref={a_ref: same_scores, b_ref: same_scores})
    h = harness_factory(evaluation_framework=evalfw, min_sample_size_per_arm=3)
    a, b = await _register_two_versions(h)
    ab_test = await h.ab_testing_service.start(
        tenant_id="acme", prompt_name="claims-summariser", version_a_id=a.id, version_b_id=b.id,
    )

    with pytest.raises(ABTestNotConclusiveError):
        await h.ab_testing_service.conclude(ab_test.id)


async def test_conclude_promotes_the_winner_and_archives_the_loser(harness_factory):
    a_ref = evaluation_ref("claims-summariser", "1")
    b_ref = evaluation_ref("claims-summariser", "2")
    evalfw = StubEvaluationFrameworkClient(scores_by_ref={a_ref: _PASSING, b_ref: _FAILING})
    h = harness_factory(evaluation_framework=evalfw, min_sample_size_per_arm=3)
    a, b = await _register_two_versions(h)
    ab_test = await h.ab_testing_service.start(
        tenant_id="acme", prompt_name="claims-summariser", version_a_id=a.id, version_b_id=b.id,
    )

    concluded = await h.ab_testing_service.conclude(ab_test.id)

    assert concluded.winner_version_id == a.id
    assert concluded.p_value is not None

    winner = await h.repository.get_prompt_version(a.id)
    loser = await h.repository.get_prompt_version(b.id)
    assert winner.status == PromptVersionStatus.ACTIVE
    assert winner.promoted_pass_rate == 1.0
    assert loser.status == PromptVersionStatus.ARCHIVED


async def test_conclude_blocks_promotion_when_evaluation_gate_fails_for_the_winner(harness_factory):
    """A clear statistical winner (a's pass rate beats b's) can still have
    failed its own most recent real evaluation run -- Evaluation
    Framework's `/gate` is the platform's single source of truth for
    that, so `conclude` must never promote around a failing gate just
    because the A/B comparison alone looks fine."""
    a_ref = evaluation_ref("claims-summariser", "1")
    b_ref = evaluation_ref("claims-summariser", "2")
    evalfw = StubEvaluationFrameworkClient(
        scores_by_ref={a_ref: _PASSING, b_ref: _FAILING},
        gate_results_by_ref={a_ref: {"overall_passed": False, "blocking_failures": ["faithfulness"]}},
    )
    h = harness_factory(evaluation_framework=evalfw, min_sample_size_per_arm=3)
    a, b = await _register_two_versions(h)
    ab_test = await h.ab_testing_service.start(
        tenant_id="acme", prompt_name="claims-summariser", version_a_id=a.id, version_b_id=b.id,
    )

    with pytest.raises(EvaluationGateFailedError):
        await h.ab_testing_service.conclude(ab_test.id)

    # Neither version was promoted/archived -- the failed gate blocks the whole
    # transition, it doesn't half-apply it.
    winner = await h.repository.get_prompt_version(a.id)
    assert winner.status == PromptVersionStatus.TESTING


async def test_conclude_promotes_when_evaluation_gate_passes_for_the_winner(harness_factory):
    a_ref = evaluation_ref("claims-summariser", "1")
    b_ref = evaluation_ref("claims-summariser", "2")
    evalfw = StubEvaluationFrameworkClient(
        scores_by_ref={a_ref: _PASSING, b_ref: _FAILING},
        gate_results_by_ref={a_ref: {"overall_passed": True, "blocking_failures": []}},
    )
    h = harness_factory(evaluation_framework=evalfw, min_sample_size_per_arm=3)
    a, b = await _register_two_versions(h)
    ab_test = await h.ab_testing_service.start(
        tenant_id="acme", prompt_name="claims-summariser", version_a_id=a.id, version_b_id=b.id,
    )

    concluded = await h.ab_testing_service.conclude(ab_test.id)

    assert concluded.winner_version_id == a.id
    winner = await h.repository.get_prompt_version(a.id)
    assert winner.status == PromptVersionStatus.ACTIVE
    assert evalfw.gate_calls == [{"tenant_id": "acme", "agent_ref": a_ref}]


async def test_conclude_promotes_when_no_eval_run_exists_yet_for_the_winner(harness_factory):
    """`gate_latest_run` returning `None` (no eval run yet) must not block
    promotion -- the same "no history is not a failure" convention
    `list_scores` already establishes, not a new, stricter one."""
    a_ref = evaluation_ref("claims-summariser", "1")
    b_ref = evaluation_ref("claims-summariser", "2")
    evalfw = StubEvaluationFrameworkClient(scores_by_ref={a_ref: _PASSING, b_ref: _FAILING})
    h = harness_factory(evaluation_framework=evalfw, min_sample_size_per_arm=3)
    a, b = await _register_two_versions(h)
    ab_test = await h.ab_testing_service.start(
        tenant_id="acme", prompt_name="claims-summariser", version_a_id=a.id, version_b_id=b.id,
    )

    concluded = await h.ab_testing_service.conclude(ab_test.id)

    winner = await h.repository.get_prompt_version(a.id)
    assert winner.status == PromptVersionStatus.ACTIVE
    assert concluded.winner_version_id == a.id


async def test_conclude_supersedes_a_previously_active_version(harness_factory):
    a_ref = evaluation_ref("claims-summariser", "1")
    b_ref = evaluation_ref("claims-summariser", "2")
    c_ref = evaluation_ref("claims-summariser", "3")
    d_ref = evaluation_ref("claims-summariser", "4")
    evalfw = StubEvaluationFrameworkClient(
        scores_by_ref={a_ref: _PASSING, b_ref: _FAILING, c_ref: _PASSING, d_ref: _FAILING},
    )
    h = harness_factory(evaluation_framework=evalfw, min_sample_size_per_arm=3)
    a, b = await _register_two_versions(h)
    first_test = await h.ab_testing_service.start(
        tenant_id="acme", prompt_name="claims-summariser", version_a_id=a.id, version_b_id=b.id,
    )
    await h.ab_testing_service.conclude(first_test.id)

    # Both sides of the second test must be fresh drafts -- a and b are now
    # active/archived respectively, neither of which can legally re-enter testing.
    c = await h.prompt_registry_service.register(
        tenant_id="acme", prompt_name="claims-summariser", version="3", template="template c",
    )
    d = await h.prompt_registry_service.register(
        tenant_id="acme", prompt_name="claims-summariser", version="4", template="template d",
    )
    second_test = await h.ab_testing_service.start(
        tenant_id="acme", prompt_name="claims-summariser", version_a_id=c.id, version_b_id=d.id,
    )
    await h.ab_testing_service.conclude(second_test.id)

    refetched_a = await h.repository.get_prompt_version(a.id)
    refetched_c = await h.repository.get_prompt_version(c.id)
    assert refetched_a.status == PromptVersionStatus.ARCHIVED  # superseded
    assert refetched_c.status == PromptVersionStatus.ACTIVE
