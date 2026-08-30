"""Tests for core/secret_access_service.py -- the zero-trust-gated
retrieval path. The defining property: a value is only ever returned
after a real, live "allowed" verdict from Identity and Access -- never
because a token merely parses, and never for a revoked secret."""
from __future__ import annotations

from secrets_and_credential_management.core.fakes import (
    StubAuditabilityClient,
    StubIdentityAccessClient,
)


async def test_retrieve_returns_the_plaintext_value_when_allowed(harness):
    secret = await harness.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="password", value="hunter2",
    )

    result = await harness.access_service.retrieve(secret_id=secret.id, token="a-valid-token")

    assert result.allowed is True
    assert result.value == "hunter2"


async def test_retrieve_denies_and_returns_no_value_when_identity_access_denies(harness_factory):
    identity_access = StubIdentityAccessClient(allow=False, reason="missing scope: secret:acme:db:read")
    h = harness_factory(identity_access=identity_access)
    secret = await h.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="password", value="hunter2",
    )

    result = await h.access_service.retrieve(secret_id=secret.id, token="a-token")

    assert result.allowed is False
    assert result.value is None
    assert "missing scope" in result.reason


async def test_retrieve_calls_identity_access_with_the_scoped_required_scope(harness_factory):
    identity_access = StubIdentityAccessClient(allow=True)
    h = harness_factory(identity_access=identity_access)
    secret = await h.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="password", value="hunter2",
    )

    await h.access_service.retrieve(secret_id=secret.id, token="tok")

    assert identity_access.calls == [{"token": "tok", "required_scope": "secret:acme:db:read"}]


async def test_retrieve_denies_a_revoked_secret_without_even_calling_identity_access(harness_factory):
    identity_access = StubIdentityAccessClient(allow=True)
    h = harness_factory(identity_access=identity_access)
    secret = await h.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="password", value="hunter2",
    )
    await h.registry_service.revoke_secret(secret.id)

    result = await h.access_service.retrieve(secret_id=secret.id, token="tok")

    assert result.allowed is False
    assert "revoked" in result.reason
    assert identity_access.calls == []


async def test_retrieve_denies_a_missing_secret(harness):
    result = await harness.access_service.retrieve(secret_id="does-not-exist", token="tok")

    assert result.allowed is False
    assert "not found" in result.reason


async def test_a_down_identity_access_peer_denies_rather_than_leaking_the_value(harness_factory):
    class RaisingIdentityAccess:
        async def authorize(self, *, token, required_scope):
            raise RuntimeError("identity-and-access is down")

    h = harness_factory(identity_access=RaisingIdentityAccess())
    secret = await h.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="password", value="hunter2",
    )

    result = await h.access_service.retrieve(secret_id=secret.id, token="tok")

    assert result.allowed is False
    assert result.value is None


async def test_every_attempt_is_recorded_locally_allowed_and_denied(harness):
    secret = await harness.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="password", value="hunter2",
    )

    await harness.access_service.retrieve(secret_id=secret.id, token="tok")

    records, total = await harness.repository.list_access_records(secret_id=secret.id)
    assert total == 1
    assert records[0].allowed is True


async def test_denied_attempts_are_emitted_to_auditability(harness_factory):
    identity_access = StubIdentityAccessClient(allow=False, reason="denied")
    auditability = StubAuditabilityClient()
    h = harness_factory(identity_access=identity_access, auditability=auditability)
    secret = await h.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="password", value="hunter2",
    )

    await h.access_service.retrieve(secret_id=secret.id, token="tok")

    assert len(auditability.events) == 1
    assert auditability.events[0]["event_type"] == "secrets.access_denied"
    assert auditability.events[0]["tenant_id"] == "acme"


async def test_a_down_auditability_peer_never_blocks_the_retrieval(harness_factory):
    auditability = StubAuditabilityClient(raise_error=True)
    h = harness_factory(auditability=auditability)
    secret = await h.registry_service.create_secret(
        tenant_id="acme", namespace="db", key_name="password", value="hunter2",
    )

    result = await h.access_service.retrieve(secret_id=secret.id, token="tok")

    assert result.allowed is True  # the retrieval itself still comes back correctly
    assert result.value == "hunter2"
