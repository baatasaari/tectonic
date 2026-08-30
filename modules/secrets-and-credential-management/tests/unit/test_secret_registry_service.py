"""Tests for core/secret_registry_service.py -- create/get/list/revoke,
and that a plaintext value never lands in the repository unencrypted."""
from __future__ import annotations

import pytest

from secrets_and_credential_management.core.domain import (
    InvalidTransitionError,
    SecretNotFoundError,
)


async def test_create_secret_stores_ciphertext_not_plaintext(harness):
    secret = await harness.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="password", value="hunter2",
    )

    version = await harness.repository.get_latest_version(secret.id)
    assert version.ciphertext != "hunter2"
    assert version.wrapped_data_key
    assert await harness.cipher.decrypt(
        ciphertext=version.ciphertext, wrapped_data_key=version.wrapped_data_key,
    ) == "hunter2"


async def test_get_secret_returns_the_created_record(harness):
    secret = await harness.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="password", value="hunter2",
    )

    fetched = await harness.registry_service.get_secret(secret.id)

    assert fetched.id == secret.id
    assert fetched.status.value == "active"


async def test_get_secret_raises_not_found_for_a_missing_id(harness):
    with pytest.raises(SecretNotFoundError):
        await harness.registry_service.get_secret("does-not-exist")


async def test_list_secrets_filters_by_tenant_and_namespace(harness):
    await harness.registry_service.create_secret(tenant_id="acme", namespace="db", key_name="p1", value="v1")
    await harness.registry_service.create_secret(tenant_id="acme", namespace="api", key_name="p2", value="v2")
    await harness.registry_service.create_secret(tenant_id="other", namespace="db", key_name="p3", value="v3")

    results, total = await harness.registry_service.list_secrets(tenant_id="acme", namespace="db")

    assert total == 1
    assert results[0].key_name == "p1"


async def test_revoke_secret_transitions_to_revoked(harness):
    secret = await harness.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="password", value="hunter2",
    )

    revoked = await harness.registry_service.revoke_secret(secret.id)

    assert revoked.status.value == "revoked"


async def test_revoke_is_one_way_a_revoked_secret_cannot_be_revoked_again(harness):
    secret = await harness.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="password", value="hunter2",
    )
    await harness.registry_service.revoke_secret(secret.id)

    with pytest.raises(InvalidTransitionError):
        await harness.registry_service.revoke_secret(secret.id)
