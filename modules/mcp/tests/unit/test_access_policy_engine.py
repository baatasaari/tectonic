"""Tests for core/access_policy_engine.py -- the deny-by-default matrix."""
from __future__ import annotations

import pytest

from mcp_gateway.core.domain import AccessDeniedError, AccessPolicyRecord, new_id


async def test_no_policy_row_denies_any_method(harness):
    with pytest.raises(AccessDeniedError):
        await harness.access_policy_engine.authorize(
            server_id="s1", tenant_id="acme", method="tools/list", tool_name=None,
        )


async def test_a_policy_with_null_allowed_tools_permits_any_tool_call(harness):
    await harness.repository.upsert_access_policy(
        AccessPolicyRecord(id=new_id(), server_id="s1", tenant_id="acme", allowed_tools=None)
    )

    await harness.access_policy_engine.authorize(server_id="s1", tenant_id="acme", method="tools/call", tool_name="search")
    # No exception -- reaching here means it was permitted.


async def test_a_policy_with_an_explicit_allow_list_permits_only_named_tools(harness):
    await harness.repository.upsert_access_policy(
        AccessPolicyRecord(id=new_id(), server_id="s1", tenant_id="acme", allowed_tools=["search"])
    )

    await harness.access_policy_engine.authorize(server_id="s1", tenant_id="acme", method="tools/call", tool_name="search")

    with pytest.raises(AccessDeniedError):
        await harness.access_policy_engine.authorize(
            server_id="s1", tenant_id="acme", method="tools/call", tool_name="delete_everything",
        )


async def test_non_tools_call_methods_only_need_the_server_level_policy_row(harness):
    await harness.repository.upsert_access_policy(
        AccessPolicyRecord(id=new_id(), server_id="s1", tenant_id="acme", allowed_tools=["search"])
    )

    # tools/list isn't tool-scoped -- having *a* policy row is enough, regardless of
    # what's in allowed_tools.
    await harness.access_policy_engine.authorize(server_id="s1", tenant_id="acme", method="tools/list", tool_name=None)


async def test_tools_call_without_a_tool_name_is_denied(harness):
    await harness.repository.upsert_access_policy(
        AccessPolicyRecord(id=new_id(), server_id="s1", tenant_id="acme", allowed_tools=["search"])
    )

    with pytest.raises(AccessDeniedError):
        await harness.access_policy_engine.authorize(server_id="s1", tenant_id="acme", method="tools/call", tool_name=None)


async def test_a_policy_for_a_different_tenant_does_not_grant_access(harness):
    await harness.repository.upsert_access_policy(
        AccessPolicyRecord(id=new_id(), server_id="s1", tenant_id="acme", allowed_tools=None)
    )

    with pytest.raises(AccessDeniedError):
        await harness.access_policy_engine.authorize(server_id="s1", tenant_id="globex", method="tools/list", tool_name=None)
