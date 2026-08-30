"""Tests for core/model_registry_service.py -- register + version history."""
from __future__ import annotations

import pytest

from llmops.core.domain import ModelVersionNotFoundError, ModelVersionStatus


async def test_register_creates_a_registered_version(harness):
    version = await harness.model_registry_service.register(
        tenant_id="acme", model_name="chat-default", version="1", artifact_ref="openai/gpt-x",
    )

    assert version.status == ModelVersionStatus.REGISTERED
    assert version.model_name == "chat-default"


async def test_get_raises_for_an_unknown_version(harness):
    with pytest.raises(ModelVersionNotFoundError):
        await harness.model_registry_service.get("does-not-exist")


async def test_list_filters_by_model_name(harness):
    await harness.model_registry_service.register(tenant_id="acme", model_name="chat-default", version="1", artifact_ref="a")
    await harness.model_registry_service.register(tenant_id="acme", model_name="embeddings-default", version="1", artifact_ref="b")

    versions, total = await harness.model_registry_service.list(tenant_id="acme", model_name="chat-default")

    assert total == 1
    assert versions[0].model_name == "chat-default"


async def test_list_paginates(harness):
    for i in range(5):
        await harness.model_registry_service.register(tenant_id="acme", model_name="m", version=str(i), artifact_ref="a")

    page1, total1 = await harness.model_registry_service.list(limit=2, offset=0)
    page2, total2 = await harness.model_registry_service.list(limit=2, offset=2)

    assert total1 == total2 == 5
    assert len(page1) == 2
    assert len(page2) == 2
    assert {v.id for v in page1}.isdisjoint({v.id for v in page2})
