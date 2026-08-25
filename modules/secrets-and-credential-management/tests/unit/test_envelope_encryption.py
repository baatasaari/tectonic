"""Tests for security/envelope_encryption.py -- pure, deterministic
cryptography, no fake needed."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from secrets_and_credential_management.security.envelope_encryption import (
    DecryptionError,
    EnvelopeCipher,
)

KEY = "TjDlTNIHnInVxA0zsGHYi6iTjBRtCSnWVcGxrYLXaYc="


def test_encrypt_decrypt_round_trip():
    cipher = EnvelopeCipher(master_key=KEY)

    ciphertext = cipher.encrypt("super-secret-db-password")

    assert ciphertext != "super-secret-db-password"
    assert cipher.decrypt(ciphertext) == "super-secret-db-password"


def test_decrypt_with_the_wrong_key_fails():
    cipher_a = EnvelopeCipher(master_key=KEY)
    cipher_b = EnvelopeCipher(master_key=Fernet.generate_key().decode())
    ciphertext = cipher_a.encrypt("value")

    with pytest.raises(DecryptionError):
        cipher_b.decrypt(ciphertext)


def test_decrypt_corrupted_ciphertext_fails():
    cipher = EnvelopeCipher(master_key=KEY)
    ciphertext = cipher.encrypt("value")
    corrupted = ciphertext[:-4] + "abcd"

    with pytest.raises(DecryptionError):
        cipher.decrypt(corrupted)
