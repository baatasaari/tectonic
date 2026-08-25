"""Tests for core/rotation_service.py -- rotate, list_due_for_rotation,
and the compliance-rate Gauge computation."""
from __future__ import annotations

from datetime import timedelta

import pytest

from secrets_and_credential_management.core.domain import (
    SecretNotFoundError,
    SecretRevokedError,
    now,
)


async def test_rotate_creates_a_new_version_and_advances_the_schedule(harness):
    secret = await harness.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="password", value="hunter2", rotation_interval_days=30,
    )
    old_due = secret.next_rotation_due_at

    rotated = await harness.rotation_service.rotate(secret_id=secret.id, new_value="new-password")

    assert rotated.current_version == 2
    assert rotated.next_rotation_due_at > old_due

    latest = await harness.repository.get_latest_version(secret.id)
    assert harness.cipher.decrypt(latest.ciphertext) == "new-password"


async def test_rotate_a_missing_secret_raises_not_found(harness):
    with pytest.raises(SecretNotFoundError):
        await harness.rotation_service.rotate(secret_id="does-not-exist", new_value="x")


async def test_rotate_a_revoked_secret_raises(harness):
    secret = await harness.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="password", value="hunter2",
    )
    await harness.registry_service.revoke_secret(secret.id)

    with pytest.raises(SecretRevokedError):
        await harness.rotation_service.rotate(secret_id=secret.id, new_value="x")


async def test_list_due_for_rotation_only_returns_overdue_active_secrets(harness):
    overdue = await harness.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="overdue", value="v",
    )
    overdue.next_rotation_due_at = now() - timedelta(days=1)
    await harness.repository.update_secret(overdue)

    await harness.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="not-due-yet", value="v",
    )

    due, total = await harness.rotation_service.list_due_for_rotation(tenant_id="acme")

    assert total == 1
    assert due[0].key_name == "overdue"


async def test_compliance_rate_with_no_active_secrets_is_none_not_fabricated(harness):
    report = await harness.rotation_service.compliance_rate(tenant_id="empty-tenant")

    assert report.total_active == 0
    assert report.compliance_rate is None


async def test_compliance_rate_reflects_overdue_fraction(harness):
    await harness.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="compliant", value="v",
    )
    overdue = await harness.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="overdue", value="v",
    )
    overdue.next_rotation_due_at = now() - timedelta(days=1)
    await harness.repository.update_secret(overdue)

    report = await harness.rotation_service.compliance_rate(tenant_id="acme")

    assert report.total_active == 2
    assert report.overdue == 1
    assert report.compliance_rate == pytest.approx(0.5)
