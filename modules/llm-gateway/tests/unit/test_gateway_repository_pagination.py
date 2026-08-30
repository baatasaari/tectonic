"""Pagination behavior for InMemoryGatewayRepository.list_virtual_keys."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from llm_gateway.core.domain import VirtualKeyRecord, new_id
from llm_gateway.core.fakes import InMemoryGatewayRepository

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _virtual_key(tenant_id: str, created_at: datetime) -> VirtualKeyRecord:
    return VirtualKeyRecord(
        id=new_id(), tenant_id=tenant_id, provider_scope=[], budget_policy_ref="budget-1",
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_list_virtual_keys_paginates_newest_first():
    repo = InMemoryGatewayRepository()
    keys = []
    for i in range(3):
        vk = await repo.create_virtual_key(_virtual_key("tenant-a", _BASE_TIME + timedelta(minutes=i)))
        keys.append(vk)

    page1, total1 = await repo.list_virtual_keys("tenant-a", limit=2, offset=0)
    assert total1 == 3
    assert [k.id for k in page1] == [keys[2].id, keys[1].id]

    page2, total2 = await repo.list_virtual_keys("tenant-a", limit=2, offset=2)
    assert total2 == 3
    assert [k.id for k in page2] == [keys[0].id]


@pytest.mark.asyncio
async def test_list_virtual_keys_empty_result_set():
    repo = InMemoryGatewayRepository()
    items, total = await repo.list_virtual_keys("tenant-with-no-keys")
    assert items == []
    assert total == 0


@pytest.mark.asyncio
async def test_list_virtual_keys_only_matches_requested_tenant():
    repo = InMemoryGatewayRepository()
    await repo.create_virtual_key(_virtual_key("tenant-a", _BASE_TIME))
    await repo.create_virtual_key(_virtual_key("tenant-b", _BASE_TIME))

    items, total = await repo.list_virtual_keys("tenant-a")
    assert total == 1
    assert items[0].tenant_id == "tenant-a"
