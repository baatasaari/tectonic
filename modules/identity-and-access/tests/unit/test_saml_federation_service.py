"""Tests for core/saml_federation_service.py -- JIT provisioning by
(tenant_id, provider_id, NameID), group-attribute -> federated_role_names
resolution, and the honest OIDC-provider rejection (the SAML sibling of
test_oidc_federation_service.py's own coverage)."""
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
        "tenant_id": "acme", "name": "ADFS", "provider_type": IdentityProviderType.SAML,
        "issuer": "https://adfs.acme.com", "client_id": "identity-and-access",
        "x509_certificate": "-----BEGIN CERTIFICATE-----\nMII...\n-----END CERTIFICATE-----",
    }
    kwargs.update(overrides)
    return await harness.identity_provider_service.register(**kwargs)


async def test_first_login_jit_provisions_a_new_identity(harness):
    provider = await _register_provider(harness)
    harness.saml_verifier.claims_by_response["resp-1"] = {
        "sub": "adfs-user-1", "email": "alice@acme.com", "name": "Alice",
    }

    identity = await harness.saml_federation_service.login(
        tenant_id="acme", provider_id=provider.id, saml_response="resp-1",
    )

    assert identity.type == IdentityType.USER
    assert identity.email == "alice@acme.com"
    assert identity.external_provider_id == provider.id
    assert identity.external_subject == "adfs-user-1"


async def test_second_login_for_the_same_subject_updates_not_duplicates(harness):
    provider = await _register_provider(harness)
    harness.saml_verifier.claims_by_response["resp-1"] = {"sub": "adfs-user-1", "email": "alice@acme.com", "name": "Alice"}
    harness.saml_verifier.claims_by_response["resp-2"] = {
        "sub": "adfs-user-1", "email": "alice2@acme.com", "name": "Alice R.",
    }

    first = await harness.saml_federation_service.login(tenant_id="acme", provider_id=provider.id, saml_response="resp-1")
    second = await harness.saml_federation_service.login(tenant_id="acme", provider_id=provider.id, saml_response="resp-2")

    assert first.id == second.id
    assert second.email == "alice2@acme.com"
    assert second.name == "Alice R."

    _, total = await harness.identity_registry_service.list(tenant_id="acme")
    assert total == 1


async def test_groups_attribute_resolves_to_federated_role_names(harness):
    provider = await _register_provider(harness)
    await harness.role_service.create(name="approver", scopes=["cards:approve"])
    await harness.group_service.register(
        tenant_id="acme", provider_id=provider.id, external_id="adfs-group-approvers", name="Approvers",
        default_role_names=["approver"],
    )
    harness.saml_verifier.claims_by_response["resp-1"] = {
        "sub": "adfs-user-1", "email": "alice@acme.com", "name": "Alice", "groups": ["adfs-group-approvers"],
    }

    identity = await harness.saml_federation_service.login(tenant_id="acme", provider_id=provider.id, saml_response="resp-1")

    assert identity.federated_role_names == ["approver"]


async def test_a_single_valued_groups_attribute_still_resolves(harness):
    """The real verifier (security/saml_verifier.py) collapses a
    single-valued SAML Attribute to a scalar, not a one-element list --
    the federation service must handle both shapes."""
    provider = await _register_provider(harness)
    await harness.group_service.register(
        tenant_id="acme", provider_id=provider.id, external_id="adfs-group-approvers", name="Approvers",
        default_role_names=["approver"],
    )
    harness.saml_verifier.claims_by_response["resp-1"] = {
        "sub": "adfs-user-1", "email": "alice@acme.com", "groups": "adfs-group-approvers",  # scalar, not a list
    }

    identity = await harness.saml_federation_service.login(tenant_id="acme", provider_id=provider.id, saml_response="resp-1")

    assert identity.federated_role_names == ["approver"]


async def test_removing_a_group_from_the_attribute_revokes_the_role_on_next_login(harness):
    provider = await _register_provider(harness)
    await harness.group_service.register(
        tenant_id="acme", provider_id=provider.id, external_id="adfs-group-approvers", name="Approvers",
        default_role_names=["approver"],
    )
    harness.saml_verifier.claims_by_response["resp-1"] = {
        "sub": "adfs-user-1", "email": "alice@acme.com", "groups": ["adfs-group-approvers"],
    }
    harness.saml_verifier.claims_by_response["resp-2"] = {"sub": "adfs-user-1", "email": "alice@acme.com", "groups": []}

    await harness.saml_federation_service.login(tenant_id="acme", provider_id=provider.id, saml_response="resp-1")
    second = await harness.saml_federation_service.login(tenant_id="acme", provider_id=provider.id, saml_response="resp-2")

    assert second.federated_role_names == []


async def test_login_against_unknown_provider_raises(harness):
    with pytest.raises(IdentityProviderNotFoundError):
        await harness.saml_federation_service.login(tenant_id="acme", provider_id="nope", saml_response="resp-1")


async def test_login_against_disabled_provider_raises(harness):
    provider = await _register_provider(harness)
    await harness.identity_provider_service.set_enabled(provider.id, False)

    with pytest.raises(FederationError):
        await harness.saml_federation_service.login(tenant_id="acme", provider_id=provider.id, saml_response="resp-1")


async def test_login_against_an_oidc_provider_raises_not_silently_accepted(harness):
    provider = await _register_provider(
        harness, provider_type=IdentityProviderType.OIDC, client_id="client-1", jwks_uri="https://acme.okta.com/jwks",
    )

    with pytest.raises(FederationError, match="oidc"):
        await harness.saml_federation_service.login(tenant_id="acme", provider_id=provider.id, saml_response="resp-1")


async def test_login_with_an_unverifiable_assertion_raises(harness):
    provider = await _register_provider(harness)

    with pytest.raises(FederationError):
        await harness.saml_federation_service.login(
            tenant_id="acme", provider_id=provider.id, saml_response="not-a-known-response",
        )


async def test_login_rejects_a_provider_from_a_different_tenant(harness):
    provider = await _register_provider(harness, tenant_id="acme")
    harness.saml_verifier.claims_by_response["resp-1"] = {"sub": "adfs-user-1", "email": "alice@acme.com"}

    with pytest.raises(IdentityProviderNotFoundError):
        await harness.saml_federation_service.login(tenant_id="globex", provider_id=provider.id, saml_response="resp-1")


async def test_login_without_a_sub_claim_raises(harness):
    provider = await _register_provider(harness)
    harness.saml_verifier.claims_by_response["resp-1"] = {"email": "alice@acme.com"}  # no "sub"

    with pytest.raises(FederationError):
        await harness.saml_federation_service.login(tenant_id="acme", provider_id=provider.id, saml_response="resp-1")
