"""Tests for security/key_management.py's `LocalStaticKeyManagementProvider`
-- pure, deterministic, no I/O, so no fake needed (the same precedent
`JWTTokenSigner` and the old single-key `EnvelopeCipher` already
established). See test_vault_key_management.py for the real Vault
Transit integration."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from secrets_and_credential_management.security.key_management import (
    KeyManagementError,
    LocalStaticKeyManagementProvider,
)

MASTER_KEY = "TjDlTNIHnInVxA0zsGHYi6iTjBRtCSnWVcGxrYLXaYc="


async def test_generate_data_key_returns_32_raw_bytes_and_a_wrapped_form():
    provider = LocalStaticKeyManagementProvider(master_key=MASTER_KEY)

    data_key, wrapped = await provider.generate_data_key()

    assert isinstance(data_key, bytes)
    assert len(data_key) == 32
    assert wrapped != data_key


async def test_decrypt_data_key_unwraps_back_to_the_same_plaintext():
    provider = LocalStaticKeyManagementProvider(master_key=MASTER_KEY)
    data_key, wrapped = await provider.generate_data_key()

    unwrapped = await provider.decrypt_data_key(wrapped)

    assert unwrapped == data_key


async def test_two_calls_generate_different_data_keys():
    provider = LocalStaticKeyManagementProvider(master_key=MASTER_KEY)

    key_a, _ = await provider.generate_data_key()
    key_b, _ = await provider.generate_data_key()

    assert key_a != key_b


async def test_decrypt_data_key_with_the_wrong_root_key_fails():
    provider_a = LocalStaticKeyManagementProvider(master_key=MASTER_KEY)
    provider_b = LocalStaticKeyManagementProvider(master_key=Fernet.generate_key().decode())
    _, wrapped = await provider_a.generate_data_key()

    with pytest.raises(KeyManagementError):
        await provider_b.decrypt_data_key(wrapped)


async def test_decrypt_data_key_with_a_corrupted_value_fails():
    provider = LocalStaticKeyManagementProvider(master_key=MASTER_KEY)
    _, wrapped = await provider.generate_data_key()

    with pytest.raises(KeyManagementError):
        await provider.decrypt_data_key(wrapped[:-4] + "abcd")
