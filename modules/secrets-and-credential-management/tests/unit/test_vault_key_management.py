"""Real end-to-end test for security/key_management.py's
`VaultTransitKeyManagementProvider`: a real client making real HTTP
requests against Vault's own documented Transit engine request/response
shapes, verified through a respx-mocked transport -- this platform's
standard "real client, mocked transport" shape for outbound HTTP
(Identity and Access's oidc_verifier.py test does the same for OIDC
JWKS). No live Vault server is reachable from this sandbox; a genuine
`vault server -dev` instance is the honest verification path left for a
real deployment, not something fabricated here -- see
security/key_management.py's own module docstring.
"""
from __future__ import annotations

import base64

import httpx
import pytest
import respx

from secrets_and_credential_management.security.key_management import (
    KeyManagementError,
    VaultTransitKeyManagementProvider,
)

VAULT_ADDR = "https://vault.internal:8200"
KEY_NAME = "tectonic-secrets"
VAULT_TOKEN = "s.test-vault-token"


def _provider() -> VaultTransitKeyManagementProvider:
    return VaultTransitKeyManagementProvider(VAULT_ADDR, vault_token=VAULT_TOKEN, key_name=KEY_NAME)


@respx.mock
async def test_generate_data_key_calls_the_real_datakey_endpoint_and_decodes_the_plaintext():
    plaintext_b64 = base64.b64encode(b"\x01" * 32).decode()
    route = respx.post(f"{VAULT_ADDR}/v1/transit/datakey/plaintext/{KEY_NAME}").mock(
        return_value=httpx.Response(200, json={
            "data": {"plaintext": plaintext_b64, "ciphertext": "vault:v1:abcdefgh"},
        }),
    )

    provider = _provider()
    data_key, wrapped = await provider.generate_data_key()

    assert route.called
    request = route.calls.last.request
    assert request.headers["X-Vault-Token"] == VAULT_TOKEN
    assert data_key == b"\x01" * 32
    assert wrapped == "vault:v1:abcdefgh"


@respx.mock
async def test_decrypt_data_key_calls_the_real_decrypt_endpoint_with_the_wrapped_value():
    plaintext_b64 = base64.b64encode(b"\x02" * 32).decode()
    route = respx.post(f"{VAULT_ADDR}/v1/transit/decrypt/{KEY_NAME}").mock(
        return_value=httpx.Response(200, json={"data": {"plaintext": plaintext_b64}}),
    )

    provider = _provider()
    data_key = await provider.decrypt_data_key("vault:v1:abcdefgh")

    assert route.called
    import json
    assert json.loads(route.calls.last.request.content) == {"ciphertext": "vault:v1:abcdefgh"}
    assert data_key == b"\x02" * 32


@respx.mock
async def test_generate_data_key_raises_key_management_error_on_vault_failure():
    respx.post(f"{VAULT_ADDR}/v1/transit/datakey/plaintext/{KEY_NAME}").mock(
        return_value=httpx.Response(403, json={"errors": ["permission denied"]}),
    )

    provider = _provider()
    with pytest.raises(KeyManagementError):
        await provider.generate_data_key()


@respx.mock
async def test_decrypt_data_key_raises_key_management_error_on_vault_failure():
    respx.post(f"{VAULT_ADDR}/v1/transit/decrypt/{KEY_NAME}").mock(
        return_value=httpx.Response(400, json={"errors": ["invalid ciphertext"]}),
    )

    provider = _provider()
    with pytest.raises(KeyManagementError):
        await provider.decrypt_data_key("not-a-real-wrapped-key")
