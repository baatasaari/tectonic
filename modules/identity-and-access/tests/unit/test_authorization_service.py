"""Tests for core/authorization_service.py -- the zero-trust authorize
check. The defining property: a revoked identity's outstanding tokens
stop authorizing immediately, even though the token's own signature and
expiry are still perfectly valid."""
from __future__ import annotations

from identity_and_access.core.fakes import StubAuditabilityClient


async def test_authorize_allows_a_valid_token_with_the_required_scope(harness):
    await harness.role_service.create(name="reader", scopes=["cards:read"])
    identity = await harness.identity_registry_service.register(
        tenant_id="acme", name="agent-1", role_names=["reader"],
    )
    issued = await harness.token_service.issue(identity_id=identity.id)

    result = await harness.authorization_service.authorize(token=issued.token, required_scope="cards:read")

    assert result.allowed is True


async def test_authorize_denies_a_missing_scope(harness):
    await harness.role_service.create(name="reader", scopes=["cards:read"])
    identity = await harness.identity_registry_service.register(
        tenant_id="acme", name="agent-1", role_names=["reader"],
    )
    issued = await harness.token_service.issue(identity_id=identity.id)

    result = await harness.authorization_service.authorize(token=issued.token, required_scope="cards:delete")

    assert result.allowed is False
    assert "missing scope" in result.reason


async def test_authorize_denies_garbage_tokens(harness):
    result = await harness.authorization_service.authorize(token="not-a-real-token", required_scope="cards:read")

    assert result.allowed is False
    assert "invalid token" in result.reason


async def test_zero_trust_a_revoked_identitys_still_valid_token_stops_authorizing(harness):
    """The defining zero-trust property: revocation is checked live on every call, not
    just at token-mint time. A token minted while the identity was active, with plenty
    of time left before its own expiry, must be denied the instant its identity is
    revoked."""
    await harness.role_service.create(name="reader", scopes=["cards:read"])
    identity = await harness.identity_registry_service.register(
        tenant_id="acme", name="agent-1", role_names=["reader"],
    )
    issued = await harness.token_service.issue(identity_id=identity.id, ttl_seconds=3600)

    before_revoke = await harness.authorization_service.authorize(token=issued.token, required_scope="cards:read")
    assert before_revoke.allowed is True

    await harness.identity_registry_service.revoke(identity.id)

    after_revoke = await harness.authorization_service.authorize(token=issued.token, required_scope="cards:read")
    assert after_revoke.allowed is False
    assert "not active" in after_revoke.reason


async def test_denials_increment_the_real_audit_trail_and_metric(harness_factory):
    auditability = StubAuditabilityClient()
    h = harness_factory(auditability=auditability)
    await h.role_service.create(name="reader", scopes=["cards:read"])
    identity = await h.identity_registry_service.register(tenant_id="acme", name="agent-1", role_names=["reader"])
    issued = await h.token_service.issue(identity_id=identity.id)

    await h.authorization_service.authorize(token=issued.token, required_scope="cards:delete")

    decisions, total = await h.repository.list_auth_decisions(identity_id=identity.id)
    assert total == 1
    assert decisions[0].allowed is False

    assert len(auditability.events) == 1
    assert auditability.events[0]["event_type"] == "identity_access.unauthorized_attempt"
    assert auditability.events[0]["tenant_id"] == "acme"


async def test_a_down_auditability_peer_never_blocks_the_auth_decision(harness_factory):
    auditability = StubAuditabilityClient(raise_error=True)
    h = harness_factory(auditability=auditability)
    await h.role_service.create(name="reader", scopes=["cards:read"])
    identity = await h.identity_registry_service.register(tenant_id="acme", name="agent-1", role_names=["reader"])
    issued = await h.token_service.issue(identity_id=identity.id)

    result = await h.authorization_service.authorize(token=issued.token, required_scope="cards:delete")

    assert result.allowed is False  # the decision itself still comes back correctly


async def test_allowed_decisions_are_recorded_too(harness):
    await harness.role_service.create(name="reader", scopes=["cards:read"])
    identity = await harness.identity_registry_service.register(
        tenant_id="acme", name="agent-1", role_names=["reader"],
    )
    issued = await harness.token_service.issue(identity_id=identity.id)

    await harness.authorization_service.authorize(token=issued.token, required_scope="cards:read")

    decisions, total = await harness.repository.list_auth_decisions(identity_id=identity.id)
    assert total == 1
    assert decisions[0].allowed is True
