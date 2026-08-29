"""Tests for core/identity_provider_service.py -- CRUD for per-tenant
OIDC/SAML federation config."""
from __future__ import annotations

import pytest

from identity_and_access.core.domain import IdentityProviderNotFoundError, IdentityProviderType


async def test_register_and_get(harness):
    provider = await harness.identity_provider_service.register(
        tenant_id="acme", name="Okta", provider_type=IdentityProviderType.OIDC,
        issuer="https://acme.okta.com", client_id="client-1", jwks_uri="https://acme.okta.com/jwks",
    )

    fetched = await harness.identity_provider_service.get(provider.id)
    assert fetched.tenant_id == "acme"
    assert fetched.enabled is True
    assert fetched.provider_type == IdentityProviderType.OIDC


async def test_get_raises_when_missing(harness):
    with pytest.raises(IdentityProviderNotFoundError):
        await harness.identity_provider_service.get("does-not-exist")


async def test_saml_provider_stores_config_only_fields(harness):
    provider = await harness.identity_provider_service.register(
        tenant_id="acme", name="ADFS", provider_type=IdentityProviderType.SAML,
        issuer="https://adfs.acme.com", sso_url="https://adfs.acme.com/sso",
        x509_certificate="-----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE-----",
    )

    assert provider.provider_type == IdentityProviderType.SAML
    assert provider.sso_url == "https://adfs.acme.com/sso"


async def test_set_enabled_toggles_and_persists(harness):
    provider = await harness.identity_provider_service.register(
        tenant_id="acme", name="Okta", provider_type=IdentityProviderType.OIDC, issuer="https://acme.okta.com",
    )

    disabled = await harness.identity_provider_service.set_enabled(provider.id, False)
    assert disabled.enabled is False

    fetched = await harness.identity_provider_service.get(provider.id)
    assert fetched.enabled is False


async def test_list_filters_by_tenant(harness):
    await harness.identity_provider_service.register(
        tenant_id="acme", name="Okta", provider_type=IdentityProviderType.OIDC, issuer="https://acme.okta.com",
    )
    await harness.identity_provider_service.register(
        tenant_id="globex", name="Azure AD", provider_type=IdentityProviderType.OIDC, issuer="https://login.microsoftonline.com/x",
    )

    providers, total = await harness.identity_provider_service.list(tenant_id="acme")
    assert total == 1
    assert providers[0].tenant_id == "acme"
