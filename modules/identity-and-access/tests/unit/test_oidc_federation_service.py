"""Tests for core/oidc_federation_service.py -- JIT provisioning by
(tenant_id, provider_id, sub), group-claim -> federated_role_names
resolution, and the honest SAML gap."""
from __future__ import annotations

import pytest

from identity_and_access.core.domain import (
    FederationError,
    IdentityProviderNotFoundError,
    IdentityProviderType,
    IdentityType,
)


async def _register_provider(harness, **overrides):
    kwargs = {
        "tenant_id": "acme", "name": "Okta", "provider_type": IdentityProviderType.OIDC,
        "issuer": "https://acme.okta.com", "client_id": "client-1", "jwks_uri": "https://acme.okta.com/jwks",
    }
    kwargs.update(overrides)
    return await harness.identity_provider_service.register(**kwargs)


async def test_first_login_jit_provisions_a_new_identity(harness):
    provider = await _register_provider(harness)
    harness.oidc_verifier.claims_by_token["tok-1"] = {
        "sub": "okta-user-1", "email": "alice@acme.com", "name": "Alice",
    }

    identity = await harness.oidc_federation_service.login(
        tenant_id="acme", provider_id=provider.id, id_token="tok-1",
    )

    assert identity.type == IdentityType.USER
    assert identity.email == "alice@acme.com"
    assert identity.external_provider_id == provider.id
    assert identity.external_subject == "okta-user-1"


async def test_second_login_for_the_same_subject_updates_not_duplicates(harness):
    provider = await _register_provider(harness)
    harness.oidc_verifier.claims_by_token["tok-1"] = {"sub": "okta-user-1", "email": "alice@acme.com", "name": "Alice"}
    harness.oidc_verifier.claims_by_token["tok-2"] = {"sub": "okta-user-1", "email": "alice2@acme.com", "name": "Alice R."}

    first = await harness.oidc_federation_service.login(tenant_id="acme", provider_id=provider.id, id_token="tok-1")
    second = await harness.oidc_federation_service.login(tenant_id="acme", provider_id=provider.id, id_token="tok-2")

    assert first.id == second.id
    assert second.email == "alice2@acme.com"
    assert second.name == "Alice R."

    _, total = await harness.identity_registry_service.list(tenant_id="acme")
    assert total == 1


async def test_groups_claim_resolves_to_federated_role_names(harness):
    provider = await _register_provider(harness)
    await harness.role_service.create(name="approver", scopes=["cards:approve"])
    await harness.group_service.register(
        tenant_id="acme", provider_id=provider.id, external_id="okta-group-approvers", name="Approvers",
        default_role_names=["approver"],
    )
    harness.oidc_verifier.claims_by_token["tok-1"] = {
        "sub": "okta-user-1", "email": "alice@acme.com", "name": "Alice", "groups": ["okta-group-approvers"],
    }

    identity = await harness.oidc_federation_service.login(tenant_id="acme", provider_id=provider.id, id_token="tok-1")

    assert identity.federated_role_names == ["approver"]


async def test_removing_a_group_from_the_claim_revokes_the_role_on_next_login(harness):
    provider = await _register_provider(harness)
    await harness.group_service.register(
        tenant_id="acme", provider_id=provider.id, external_id="okta-group-approvers", name="Approvers",
        default_role_names=["approver"],
    )
    harness.oidc_verifier.claims_by_token["tok-1"] = {
        "sub": "okta-user-1", "email": "alice@acme.com", "name": "Alice", "groups": ["okta-group-approvers"],
    }
    harness.oidc_verifier.claims_by_token["tok-2"] = {
        "sub": "okta-user-1", "email": "alice@acme.com", "name": "Alice", "groups": [],
    }

    await harness.oidc_federation_service.login(tenant_id="acme", provider_id=provider.id, id_token="tok-1")
    second = await harness.oidc_federation_service.login(tenant_id="acme", provider_id=provider.id, id_token="tok-2")

    assert second.federated_role_names == []


async def test_login_against_unknown_provider_raises(harness):
    with pytest.raises(IdentityProviderNotFoundError):
        await harness.oidc_federation_service.login(tenant_id="acme", provider_id="nope", id_token="tok-1")


async def test_login_against_disabled_provider_raises(harness):
    provider = await _register_provider(harness)
    await harness.identity_provider_service.set_enabled(provider.id, False)

    with pytest.raises(FederationError):
        await harness.oidc_federation_service.login(tenant_id="acme", provider_id=provider.id, id_token="tok-1")


async def test_login_against_a_saml_provider_raises_not_silently_accepted(harness):
    provider = await _register_provider(
        harness, provider_type=IdentityProviderType.SAML, sso_url="https://adfs.acme.com/sso",
        x509_certificate="cert",
    )

    with pytest.raises(FederationError, match="SAML"):
        await harness.oidc_federation_service.login(tenant_id="acme", provider_id=provider.id, id_token="tok-1")


async def test_login_with_an_unverifiable_token_raises(harness):
    provider = await _register_provider(harness)

    with pytest.raises(FederationError):
        await harness.oidc_federation_service.login(tenant_id="acme", provider_id=provider.id, id_token="not-a-known-token")


async def test_login_rejects_a_provider_from_a_different_tenant(harness):
    provider = await _register_provider(harness, tenant_id="acme")
    harness.oidc_verifier.claims_by_token["tok-1"] = {"sub": "okta-user-1", "email": "alice@acme.com"}

    with pytest.raises(IdentityProviderNotFoundError):
        await harness.oidc_federation_service.login(tenant_id="globex", provider_id=provider.id, id_token="tok-1")
