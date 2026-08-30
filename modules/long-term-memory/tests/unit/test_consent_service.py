"""Tests for core/consent_service.py -- grant/revoke consent for
(tenant_id, scope, purpose), the durable ConsentRecord audit trail
(memory governance foundation)."""
from __future__ import annotations

import pytest

from long_term_memory.core.domain import ConsentBasis, ConsentRecordNotFoundError


async def test_grant_creates_an_active_consent_record(harness):
    record = await harness.consent_service.grant(
        tenant_id="t1", scope="user:alice", purpose="personalization", basis=ConsentBasis.EXPLICIT,
        granted_by="alice",
    )
    assert record.revoked_at is None
    assert record.granted_by == "alice"
    assert await harness.consent_service.is_active("t1", "user:alice", "personalization") is True


async def test_granting_an_already_active_consent_is_idempotent(harness):
    first = await harness.consent_service.grant(
        tenant_id="t1", scope="user:alice", purpose="personalization", basis=ConsentBasis.EXPLICIT,
    )
    second = await harness.consent_service.grant(
        tenant_id="t1", scope="user:alice", purpose="personalization", basis=ConsentBasis.EXPLICIT,
    )
    assert first.id == second.id
    records = await harness.consent_service.list_for_scope("t1", "user:alice")
    assert len(records) == 1


async def test_revoke_marks_the_record_revoked_in_place(harness):
    consent = await harness.consent_service.grant(
        tenant_id="t1", scope="user:alice", purpose="personalization", basis=ConsentBasis.EXPLICIT,
    )
    revoked = await harness.consent_service.revoke(tenant_id="t1", consent_id=consent.id)

    assert revoked.id == consent.id  # same row, updated in place
    assert revoked.revoked_at is not None
    assert await harness.consent_service.is_active("t1", "user:alice", "personalization") is False
    records = await harness.consent_service.list_for_scope("t1", "user:alice")
    assert len(records) == 1


async def test_revoke_raises_for_an_unknown_consent_id(harness):
    with pytest.raises(ConsentRecordNotFoundError):
        await harness.consent_service.revoke(tenant_id="t1", consent_id="does-not-exist")


async def test_grant_after_revoke_produces_a_new_active_record(harness):
    """Re-granting after a revoke is a genuinely new grant event -- it must
    get its own row, not resurrect the old, now-revoked one."""
    first = await harness.consent_service.grant(
        tenant_id="t1", scope="user:alice", purpose="personalization", basis=ConsentBasis.EXPLICIT,
    )
    await harness.consent_service.revoke(tenant_id="t1", consent_id=first.id)
    second = await harness.consent_service.grant(
        tenant_id="t1", scope="user:alice", purpose="personalization", basis=ConsentBasis.EXPLICIT,
    )

    assert second.id != first.id
    assert await harness.consent_service.is_active("t1", "user:alice", "personalization") is True
    records = await harness.consent_service.list_for_scope("t1", "user:alice")
    assert len(records) == 2


async def test_consent_is_scoped_per_tenant(harness):
    await harness.consent_service.grant(
        tenant_id="t1", scope="user:alice", purpose="personalization", basis=ConsentBasis.EXPLICIT,
    )
    assert await harness.consent_service.is_active("t2", "user:alice", "personalization") is False
