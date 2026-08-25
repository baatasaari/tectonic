"""Tests for core/prompt_registry_service.py -- register/list/get."""
from __future__ import annotations

import pytest

from promptops.core.domain import PromptVersionNotFoundError, PromptVersionStatus


async def test_register_persists_a_draft_version(harness):
    version = await harness.prompt_registry_service.register(
        tenant_id="acme", prompt_name="claims-summariser", version="1", template="Summarise: {input}",
    )

    assert version.status == PromptVersionStatus.DRAFT
    assert version.tenant_id == "acme"
    assert version.prompt_name == "claims-summariser"

    fetched = await harness.prompt_registry_service.get(version.id)
    assert fetched.id == version.id


async def test_get_raises_when_missing(harness):
    with pytest.raises(PromptVersionNotFoundError):
        await harness.prompt_registry_service.get("does-not-exist")


async def test_list_filters_by_tenant_and_prompt_name(harness):
    await harness.prompt_registry_service.register(tenant_id="acme", prompt_name="a", version="1", template="t")
    await harness.prompt_registry_service.register(tenant_id="acme", prompt_name="b", version="1", template="t")
    await harness.prompt_registry_service.register(tenant_id="other", prompt_name="a", version="1", template="t")

    results, total = await harness.prompt_registry_service.list(tenant_id="acme", prompt_name="a")

    assert total == 1
    assert results[0].prompt_name == "a"
