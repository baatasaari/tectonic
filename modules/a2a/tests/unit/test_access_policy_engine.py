"""Tests for core/access_policy_engine.py -- the deny-by-default matrix."""
from __future__ import annotations

import pytest

from a2a_gateway.core.domain import A2AAccessPolicyRecord, AccessDeniedError, new_id


async def test_no_policy_row_denies_any_skill(harness):
    with pytest.raises(AccessDeniedError):
        await harness.access_policy_engine.authorize(caller_agent_id="peer-1", tenant_id="acme", skill_id="summarize")


async def test_a_policy_with_null_allowed_skills_permits_any_skill(harness):
    await harness.repository.upsert_access_policy(
        A2AAccessPolicyRecord(id=new_id(), caller_agent_id="peer-1", tenant_id="acme", allowed_skills=None)
    )

    await harness.access_policy_engine.authorize(caller_agent_id="peer-1", tenant_id="acme", skill_id="summarize")
    # No exception -- reaching here means it was permitted.


async def test_a_policy_with_an_explicit_allow_list_permits_only_named_skills(harness):
    await harness.repository.upsert_access_policy(
        A2AAccessPolicyRecord(id=new_id(), caller_agent_id="peer-1", tenant_id="acme", allowed_skills=["summarize"])
    )

    await harness.access_policy_engine.authorize(caller_agent_id="peer-1", tenant_id="acme", skill_id="summarize")

    with pytest.raises(AccessDeniedError):
        await harness.access_policy_engine.authorize(caller_agent_id="peer-1", tenant_id="acme", skill_id="delete_everything")


async def test_a_policy_for_a_different_tenant_does_not_grant_access(harness):
    await harness.repository.upsert_access_policy(
        A2AAccessPolicyRecord(id=new_id(), caller_agent_id="peer-1", tenant_id="acme", allowed_skills=None)
    )

    with pytest.raises(AccessDeniedError):
        await harness.access_policy_engine.authorize(caller_agent_id="peer-1", tenant_id="globex", skill_id="summarize")
