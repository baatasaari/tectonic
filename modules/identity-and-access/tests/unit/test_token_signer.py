"""Tests for security/token_signer.py -- pure, deterministic
cryptography, no fake needed."""
from __future__ import annotations

import time

import pytest

from identity_and_access.security.token_signer import JWTTokenSigner, TokenVerificationError

SECRET = "test-signing-secret-at-least-32-bytes-long"


def test_mint_and_verify_round_trip():
    signer = JWTTokenSigner(signing_secret=SECRET)
    token = signer.mint(identity_id="i1", tenant_id="acme", scopes=["cards:read", "cards:write"], ttl_seconds=60)

    claims = signer.verify(token)

    assert claims["sub"] == "i1"
    assert claims["tenant_id"] == "acme"
    assert claims["scopes"] == ["cards:read", "cards:write"]


def test_mint_with_no_scopes_verifies_to_an_empty_list():
    signer = JWTTokenSigner(signing_secret=SECRET)
    token = signer.mint(identity_id="i1", tenant_id="acme", scopes=[], ttl_seconds=60)

    claims = signer.verify(token)

    assert claims["scopes"] == []


def test_verify_rejects_an_expired_token():
    signer = JWTTokenSigner(signing_secret=SECRET)
    token = signer.mint(identity_id="i1", tenant_id="acme", scopes=[], ttl_seconds=-1)

    with pytest.raises(TokenVerificationError) as exc_info:
        signer.verify(token)
    assert "expired" in exc_info.value.reason


def test_verify_rejects_a_token_signed_with_a_different_secret():
    signer_a = JWTTokenSigner(signing_secret=SECRET)
    signer_b = JWTTokenSigner(signing_secret="a-totally-different-secret-value-here")
    token = signer_a.mint(identity_id="i1", tenant_id="acme", scopes=[], ttl_seconds=60)

    with pytest.raises(TokenVerificationError):
        signer_b.verify(token)


def test_verify_rejects_garbage():
    signer = JWTTokenSigner(signing_secret=SECRET)

    with pytest.raises(TokenVerificationError):
        signer.verify("not-a-real-token")


def test_minted_token_expires_ttl_seconds_from_now():
    signer = JWTTokenSigner(signing_secret=SECRET)
    before = int(time.time())
    token = signer.mint(identity_id="i1", tenant_id="acme", scopes=[], ttl_seconds=120)

    import jwt as pyjwt
    claims = pyjwt.decode(token, SECRET, algorithms=["HS256"])

    assert before + 120 <= claims["exp"] <= before + 121
