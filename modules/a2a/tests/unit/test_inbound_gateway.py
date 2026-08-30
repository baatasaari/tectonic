"""Tests for core/inbound_gateway.py -- the inbound half: policy
enforcement, skill -> definition mapping, dispatch into Workflow Engine."""
from __future__ import annotations

import pytest

from a2a_gateway.core.domain import (
    A2AAccessPolicyRecord,
    AccessDeniedError,
    TaskDirection,
    TaskStatus,
    UnknownSkillError,
    new_id,
)
from a2a_gateway.core.fakes import StubWorkflowEngineClient


async def test_accept_denies_a_caller_with_no_policy_row(harness):
    with pytest.raises(AccessDeniedError):
        await harness.inbound_gateway.accept(
            tenant_id="acme", caller_agent_id="peer-1", peer_agent_url="http://peer",
            skill_id="summarize", input_message={},
        )


async def test_accept_rejects_a_skill_this_platform_does_not_publish(harness):
    await harness.repository.upsert_access_policy(
        A2AAccessPolicyRecord(id=new_id(), caller_agent_id="peer-1", tenant_id="acme", allowed_skills=None)
    )

    with pytest.raises(UnknownSkillError):
        await harness.inbound_gateway.accept(
            tenant_id="acme", caller_agent_id="peer-1", peer_agent_url="http://peer",
            skill_id="not-a-real-skill", input_message={},
        )


async def test_accept_dispatches_to_workflow_engine_and_persists_a_working_task(harness):
    await harness.repository.upsert_access_policy(
        A2AAccessPolicyRecord(id=new_id(), caller_agent_id="peer-1", tenant_id="acme", allowed_skills=None)
    )

    task = await harness.inbound_gateway.accept(
        tenant_id="acme", caller_agent_id="peer-1", peer_agent_url="http://peer",
        skill_id="summarize", input_message={"text": "hello"},
    )

    assert task.direction == TaskDirection.INBOUND
    assert task.status == TaskStatus.WORKING
    assert task.output_artifacts[0]["workflow_instance_id"] == "wf-instance-1"
    assert harness.workflow_client.calls[0]["definition_id"] == "def-summarize"
    assert harness.workflow_client.calls[0]["tenant_id"] == "acme"


async def test_accept_marks_the_task_failed_when_workflow_engine_rejects_it(harness_factory):
    workflow_client = StubWorkflowEngineClient(error=RuntimeError("definition not found"))
    harness = harness_factory(workflow_client=workflow_client)
    await harness.repository.upsert_access_policy(
        A2AAccessPolicyRecord(id=new_id(), caller_agent_id="peer-1", tenant_id="acme", allowed_skills=None)
    )

    task = await harness.inbound_gateway.accept(
        tenant_id="acme", caller_agent_id="peer-1", peer_agent_url="http://peer",
        skill_id="summarize", input_message={},
    )

    assert task.status == TaskStatus.FAILED
    assert "definition not found" in task.error
