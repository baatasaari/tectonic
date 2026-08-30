"""Real end-to-end test for security/oidc_verifier.py: a genuine RSA
keypair, a genuine RS256-signed PyJWT token, and a respx-mocked JWKS
endpoint -- real client, mocked transport, this platform's standard
shape for outbound HTTP tests. `StubOidcTokenVerifier` (core/fakes.py)
covers OidcFederationService's own business logic without any of this;
this file is the one place the real cryptography actually gets
exercised.
"""
from __future__ import annotations

import time

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa

from identity_and_access.core.domain import (
    FederationError,
    IdentityProviderRecord,
    IdentityProviderType,
)
from identity_and_access.security.oidc_verifier import HTTPOidcTokenVerifier

ISSUER = "https://acme.okta.com"
AUDIENCE = "client-1"
JWKS_URI = "https://acme.okta.com/jwks"
KID = "test-key-1"


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _provider() -> IdentityProviderRecord:
    return IdentityProviderRecord(
        id="p1", tenant_id="acme", name="Okta", provider_type=IdentityProviderType.OIDC, issuer=ISSUER,
        client_id=AUDIENCE, jwks_uri=JWKS_URI,
    )


def _sign(rsa_key, *, claims: dict) -> str:
    return jwt.encode(claims, rsa_key, algorithm="RS256", headers={"kid": KID})


async def _make_jwks(rsa_key) -> dict:
    from jwt.algorithms import RSAAlgorithm

    jwk_dict = RSAAlgorithm.to_jwk(rsa_key.public_key(), as_dict=True)
    jwk_dict["kid"] = KID
    jwk_dict["use"] = "sig"
    jwk_dict["alg"] = "RS256"
    return {"keys": [jwk_dict]}


@respx.mock
async def test_verify_accepts_a_genuinely_valid_token(rsa_key):
    jwks = await _make_jwks(rsa_key)
    respx.get(JWKS_URI).mock(return_value=httpx.Response(200, json=jwks))
    now = int(time.time())
    token = _sign(rsa_key, claims={"sub": "okta-user-1", "iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 300})

    async with httpx.AsyncClient() as client:
        verifier = HTTPOidcTokenVerifier(client=client)
        claims = await verifier.verify(id_token=token, provider=_provider())

    assert claims["sub"] == "okta-user-1"


@respx.mock
async def test_verify_rejects_a_token_signed_with_a_different_key(rsa_key):
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwks = await _make_jwks(rsa_key)  # JWKS only publishes the real key
    respx.get(JWKS_URI).mock(return_value=httpx.Response(200, json=jwks))
    now = int(time.time())
    token = _sign(other_key, claims={"sub": "attacker", "iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 300})

    async with httpx.AsyncClient() as client:
        verifier = HTTPOidcTokenVerifier(client=client)
        with pytest.raises(FederationError):
            await verifier.verify(id_token=token, provider=_provider())


@respx.mock
async def test_verify_rejects_wrong_issuer(rsa_key):
    jwks = await _make_jwks(rsa_key)
    respx.get(JWKS_URI).mock(return_value=httpx.Response(200, json=jwks))
    now = int(time.time())
    token = _sign(
        rsa_key, claims={"sub": "okta-user-1", "iss": "https://not-acme.example.com", "aud": AUDIENCE, "iat": now, "exp": now + 300},
    )

    async with httpx.AsyncClient() as client:
        verifier = HTTPOidcTokenVerifier(client=client)
        with pytest.raises(FederationError):
            await verifier.verify(id_token=token, provider=_provider())


@respx.mock
async def test_verify_rejects_an_expired_token(rsa_key):
    jwks = await _make_jwks(rsa_key)
    respx.get(JWKS_URI).mock(return_value=httpx.Response(200, json=jwks))
    now = int(time.time())
    token = _sign(rsa_key, claims={"sub": "okta-user-1", "iss": ISSUER, "aud": AUDIENCE, "iat": now - 600, "exp": now - 300})

    async with httpx.AsyncClient() as client:
        verifier = HTTPOidcTokenVerifier(client=client)
        with pytest.raises(FederationError):
            await verifier.verify(id_token=token, provider=_provider())


@respx.mock
async def test_verify_raises_when_jwks_fetch_fails(rsa_key):
    respx.get(JWKS_URI).mock(return_value=httpx.Response(500))
    token = _sign(rsa_key, claims={"sub": "okta-user-1", "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 300})

    async with httpx.AsyncClient() as client:
        verifier = HTTPOidcTokenVerifier(client=client)
        with pytest.raises(FederationError):
            await verifier.verify(id_token=token, provider=_provider())


async def test_verify_raises_when_provider_has_no_jwks_uri(rsa_key):
    provider = IdentityProviderRecord(
        id="p1", tenant_id="acme", name="Okta", provider_type=IdentityProviderType.OIDC, issuer=ISSUER,
    )
    token = _sign(rsa_key, claims={"sub": "okta-user-1", "iss": ISSUER, "exp": int(time.time()) + 300})

    async with httpx.AsyncClient() as client:
        verifier = HTTPOidcTokenVerifier(client=client)
        with pytest.raises(FederationError):
            await verifier.verify(id_token=token, provider=provider)
