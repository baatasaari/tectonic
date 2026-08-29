"""Tests for security/envelope_encryption.py -- real envelope
encryption (a fresh data key per encrypt call, wrapped by a
KeyManagementProvider) exercised against LocalStaticKeyManagementProvider,
the pure/no-I/O implementation. See test_key_management.py for that
provider's own tests and test_vault_key_management.py for the real
Vault Transit integration."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from secrets_and_credential_management.security.envelope_encryption import (
    DecryptionError,
    EnvelopeCipher,
)
from secrets_and_credential_management.security.key_management import (
    LocalStaticKeyManagementProvider,
)

KEY = "TjDlTNIHnInVxA0zsGHYi6iTjBRtCSnWVcGxrYLXaYc="


def _cipher(master_key: str = KEY) -> EnvelopeCipher:
    return EnvelopeCipher(key_provider=LocalStaticKeyManagementProvider(master_key=master_key))


async def test_encrypt_decrypt_round_trip():
    cipher = _cipher()

    ciphertext, wrapped_data_key = await cipher.encrypt("super-secret-db-password")

    assert ciphertext != "super-secret-db-password"
    assert wrapped_data_key
    assert await cipher.decrypt(ciphertext=ciphertext, wrapped_data_key=wrapped_data_key) == "super-secret-db-password"


async def test_two_encrypts_of_the_same_value_use_different_data_keys():
    # Real envelope encryption mints a fresh data key every call -- two encryptions of
    # the same plaintext must not even share a wrapped key, let alone ciphertext.
    cipher = _cipher()

    ciphertext_a, wrapped_a = await cipher.encrypt("same-value")
    ciphertext_b, wrapped_b = await cipher.encrypt("same-value")

    assert wrapped_a != wrapped_b
    assert ciphertext_a != ciphertext_b


async def test_decrypt_with_the_wrong_root_key_fails():
    # A wrong ROOT key fails one layer earlier than a wrong DATA key: unwrapping the
    # per-version wrapped_data_key itself fails (KeyManagementError), before Fernet
    # ever gets a chance to try decrypting the payload (DecryptionError) -- see
    # test_decrypt_corrupted_ciphertext_fails below for that other layer.
    from secrets_and_credential_management.security.key_management import KeyManagementError

    cipher_a = _cipher()
    cipher_b = _cipher(master_key=Fernet.generate_key().decode())
    ciphertext, wrapped_data_key = await cipher_a.encrypt("value")

    with pytest.raises(KeyManagementError):
        await cipher_b.decrypt(ciphertext=ciphertext, wrapped_data_key=wrapped_data_key)


async def test_decrypt_corrupted_ciphertext_fails():
    cipher = _cipher()
    ciphertext, wrapped_data_key = await cipher.encrypt("value")
    corrupted = ciphertext[:-4] + "abcd"

    with pytest.raises(DecryptionError):
        await cipher.decrypt(ciphertext=corrupted, wrapped_data_key=wrapped_data_key)


async def test_decrypt_with_a_corrupted_wrapped_data_key_fails():
    from secrets_and_credential_management.security.key_management import KeyManagementError

    cipher = _cipher()
    ciphertext, wrapped_data_key = await cipher.encrypt("value")
    corrupted_wrapped = wrapped_data_key[:-4] + "abcd"

    with pytest.raises(KeyManagementError):
        await cipher.decrypt(ciphertext=ciphertext, wrapped_data_key=corrupted_wrapped)
