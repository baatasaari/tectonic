"""Tests for core/legal_hold_service.py -- place/release a legal hold on
(tenant_id, scope), the durable LegalHoldRecord audit trail (memory
governance foundation). Actual erasure-blocking enforcement is proven in
tests/unit/test_forgetting.py; this file covers the hold records
themselves.
"""
from __future__ import annotations

import pytest

from long_term_memory.core.domain import LegalHoldNotFoundError


async def test_place_creates_an_active_hold(harness):
    hold = await harness.legal_hold_service.place(tenant_id="t1", scope="user:alice", reason="active litigation")
    assert hold.released_at is None
    assert await harness.legal_hold_service.is_active("t1", "user:alice") is True


async def test_placing_a_hold_on_an_already_held_scope_is_idempotent(harness):
    first = await harness.legal_hold_service.place(tenant_id="t1", scope="user:alice", reason="litigation A")
    second = await harness.legal_hold_service.place(tenant_id="t1", scope="user:alice", reason="litigation B")
    assert first.id == second.id
    holds = await harness.legal_hold_service.list_for_scope("t1", "user:alice")
    assert len(holds) == 1


async def test_release_marks_the_hold_released_in_place(harness):
    hold = await harness.legal_hold_service.place(tenant_id="t1", scope="user:alice", reason="active litigation")
    released = await harness.legal_hold_service.release(tenant_id="t1", hold_id=hold.id)

    assert released.id == hold.id  # same row, updated in place
    assert released.released_at is not None
    assert await harness.legal_hold_service.is_active("t1", "user:alice") is False
    holds = await harness.legal_hold_service.list_for_scope("t1", "user:alice")
    assert len(holds) == 1


async def test_release_raises_for_an_unknown_hold_id(harness):
    with pytest.raises(LegalHoldNotFoundError):
        await harness.legal_hold_service.release(tenant_id="t1", hold_id="does-not-exist")


async def test_place_after_release_produces_a_new_active_hold(harness):
    first = await harness.legal_hold_service.place(tenant_id="t1", scope="user:alice", reason="litigation A")
    await harness.legal_hold_service.release(tenant_id="t1", hold_id=first.id)
    second = await harness.legal_hold_service.place(tenant_id="t1", scope="user:alice", reason="litigation B")

    assert second.id != first.id
    assert await harness.legal_hold_service.is_active("t1", "user:alice") is True
    holds = await harness.legal_hold_service.list_for_scope("t1", "user:alice")
    assert len(holds) == 2


async def test_legal_hold_is_scoped_per_tenant(harness):
    await harness.legal_hold_service.place(tenant_id="t1", scope="user:alice", reason="active litigation")
    assert await harness.legal_hold_service.is_active("t2", "user:alice") is False
