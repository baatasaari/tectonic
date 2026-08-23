from __future__ import annotations

import pytest

from workflow_engine.core.domain import InstanceStatus, StepStatus, WorkflowInstanceRecord, new_id
from workflow_engine.core.fakes import StubGuardrailsClient
from workflow_engine.core.parser import parse_and_validate
from workflow_engine.core.symbolic import SymbolicRule

pytestmark = pytest.mark.asyncio


def _instance(definition_id: str = "def-1") -> WorkflowInstanceRecord:
    return WorkflowInstanceRecord(
        id=new_id(),
        definition_id=definition_id,
        definition_version=1,
        tenant_id="tenant-a",
        trace_id="trace-1",
        context={"amount": 5000},
    )


async def test_happy_path_symbolic_then_neural_completes(harness):
    harness.symbolic_executor.register_ruleset(
        "eligibility", [SymbolicRule(id="always", when="True", then={"decision": "eligible"})]
    )
    schema = {
        "nodes": [
            {"id": "step_1", "execution_mode": "symbolic", "config": {"symbolic_rule_ref": "eligibility"}},
            {"id": "step_2", "execution_mode": "neural", "confidence_threshold": 0.5, "config": {"agent_ref": "a1"}},
        ],
        "edges": [{"from": "step_1", "to": "step_2"}],
        "entry_point": "step_1",
        "termination_points": ["step_2"],
    }
    graph = parse_and_validate(schema)
    instance = await harness.repository.create_instance(_instance())

    result = await harness.scheduler.start(instance, graph)

    assert result.status == InstanceStatus.COMPLETED
    assert result.context["step_1"]["decision"] == "eligible"
    steps = await harness.repository.list_step_executions(result.id)
    assert {s.step_id: s.status for s in steps} == {"step_1": StepStatus.COMPLETED, "step_2": StepStatus.COMPLETED}
    event_types = [e["event_type"] for _, e in harness.event_publisher.published]
    assert "workflow.started" in event_types
    assert "workflow.completed" in event_types
    assert event_types.count("step.completed") == 2


async def test_low_confidence_pauses_for_approval_then_resumes(harness):
    harness.llm_gateway.default_confidence = 0.3
    schema = {
        "nodes": [
            {"id": "step_1", "execution_mode": "neural", "confidence_threshold": 0.8, "config": {"agent_ref": "a1"}},
        ],
        "edges": [],
        "entry_point": "step_1",
        "termination_points": ["step_1"],
    }
    graph = parse_and_validate(schema)
    instance = await harness.repository.create_instance(_instance())

    paused = await harness.scheduler.start(instance, graph)

    assert paused.status == InstanceStatus.PAUSED_FOR_APPROVAL
    assert paused.current_step_ids == ["step_1"]
    assert len(harness.human_oversight.requests) == 1
    approval_events = [e for _, e in harness.event_publisher.published if e["event_type"] == "approval.requested"]
    assert len(approval_events) == 1

    completed = await harness.scheduler.resume_after_approval(paused, graph, approved=True)

    assert completed.status == InstanceStatus.COMPLETED
    steps = await harness.repository.list_step_executions(completed.id)
    assert steps[0].status == StepStatus.COMPLETED


async def test_rejected_approval_with_no_fallback_fails_workflow(harness):
    harness.llm_gateway.default_confidence = 0.1
    schema = {
        "nodes": [
            {"id": "step_1", "execution_mode": "neural", "confidence_threshold": 0.9, "config": {"agent_ref": "a1"}},
        ],
        "edges": [],
        "entry_point": "step_1",
        "termination_points": ["step_1"],
    }
    graph = parse_and_validate(schema)
    instance = await harness.repository.create_instance(_instance())

    paused = await harness.scheduler.start(instance, graph)
    assert paused.status == InstanceStatus.PAUSED_FOR_APPROVAL

    result = await harness.scheduler.resume_after_approval(paused, graph, approved=False)

    assert result.status == InstanceStatus.FAILED


async def test_step_failure_exhausts_retries_then_replans_to_fallback(harness_factory):
    # A guardrails client that always blocks makes the neural step fail
    # deterministically on every attempt, forcing retry exhaustion.
    class AlwaysBlockGuardrails(StubGuardrailsClient):
        async def check(self, *, content, policy_profile, tenant_id):
            return False, {"violations": ["blocked-for-test"]}

    harness = harness_factory(guardrails=AlwaysBlockGuardrails())

    schema = {
        "nodes": [
            {
                "id": "step_1",
                "execution_mode": "neural",
                "confidence_threshold": 0.5,
                "config": {"agent_ref": "a1", "replan_fallback_step_id": "step_1_fallback"},
                "retry_policy": {"max_retries": 1, "backoff_strategy": "none"},
            },
            {"id": "step_1_fallback", "execution_mode": "symbolic", "config": {"symbolic_rule_ref": "fallback_rule"}},
        ],
        "edges": [],
        "entry_point": "step_1",
        # step_1 is listed as a termination point purely to satisfy the
        # dead-end check for its (never-taken-in-this-test) success path;
        # every reachable run through this test always fails step_1 and
        # exits via the replanned fallback instead.
        "termination_points": ["step_1", "step_1_fallback"],
    }
    graph = parse_and_validate(schema)
    harness.symbolic_executor.register_ruleset(
        "fallback_rule", [SymbolicRule(id="always", when="True", then={"decision": "fallback_used"})]
    )
    instance = await harness.repository.create_instance(_instance())

    result = await harness.scheduler.start(instance, graph)

    assert result.status == InstanceStatus.COMPLETED
    assert result.context["step_1_fallback"]["decision"] == "fallback_used"
    assert len(harness.repository.replan_events) == 1
    replan_event = harness.repository.replan_events[0]
    assert replan_event.original_step_id == "step_1"
    steps = await harness.repository.list_step_executions(result.id)
    failed_step = next(s for s in steps if s.step_id == "step_1")
    assert failed_step.retry_count == 1


async def test_step_failure_with_no_fallback_fails_workflow(harness_factory):
    class AlwaysBlockGuardrails(StubGuardrailsClient):
        async def check(self, *, content, policy_profile, tenant_id):
            return False, {"violations": ["blocked-for-test"]}

    harness = harness_factory(guardrails=AlwaysBlockGuardrails())

    schema = {
        "nodes": [
            {
                "id": "step_1",
                "execution_mode": "neural",
                "config": {"agent_ref": "a1"},
                "retry_policy": {"max_retries": 0, "backoff_strategy": "none"},
            },
        ],
        "edges": [],
        "entry_point": "step_1",
        "termination_points": ["step_1"],
    }
    graph = parse_and_validate(schema)
    instance = await harness.repository.create_instance(_instance())

    result = await harness.scheduler.start(instance, graph)

    assert result.status == InstanceStatus.FAILED


async def test_conditional_edges_route_correctly(harness):
    schema = {
        "nodes": [
            {"id": "step_1", "execution_mode": "symbolic", "config": {"symbolic_rule_ref": "r1"}},
            {"id": "step_high", "execution_mode": "symbolic", "config": {"symbolic_rule_ref": "r_high"}},
            {"id": "step_low", "execution_mode": "symbolic", "config": {"symbolic_rule_ref": "r_low"}},
        ],
        "edges": [
            {"from": "step_1", "to": "step_high", "condition": "step_1['decision'] == 'high'"},
            {"from": "step_1", "to": "step_low", "condition": "step_1['decision'] == 'low'"},
        ],
        "entry_point": "step_1",
        "termination_points": ["step_high", "step_low"],
    }
    graph = parse_and_validate(schema)
    harness.symbolic_executor.register_ruleset(
        "r1", [SymbolicRule(id="always", when="amount > 1000", then={"decision": "high"})]
    )
    harness.symbolic_executor.register_ruleset("r_high", [SymbolicRule(id="always", when="True", then={})])
    harness.symbolic_executor.register_ruleset("r_low", [SymbolicRule(id="always", when="True", then={})])
    instance = await harness.repository.create_instance(_instance())  # context={"amount": 5000}

    result = await harness.scheduler.start(instance, graph)

    assert result.status == InstanceStatus.COMPLETED
    steps = await harness.repository.list_step_executions(result.id)
    step_ids = {s.step_id for s in steps}
    assert step_ids == {"step_1", "step_high"}
