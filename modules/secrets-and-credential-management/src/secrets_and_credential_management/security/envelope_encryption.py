"""Envelope Cipher (LLD §Level 1 "Encryption at rest"): the one tool
that actually keeps a stored secret from being a plaintext credential
list. Every value this module ever writes to Postgres passes through
`encrypt` first; `decrypt` only ever runs after a real, live
`authorize` check has already passed (see `core/secret_access_service.py`).

Real *envelope* encryption, not a single static key: every `encrypt`
call generates a fresh, random 32-byte data key, uses it once (via
`Fernet`, real AES-128-CBC + HMAC) to encrypt the value, and returns
that data key *wrapped* by whatever `KeyManagementProvider`
(`security/key_management.py`) is configured -- a managed KMS/Vault
root key in production, never persisted or reused as-is. `decrypt`
first asks the provider to unwrap the version's own wrapped data key
back to plaintext, then decrypts with it. Each `SecretVersionRecord`
carries its own wrapped data key, so compromising one version's
ciphertext (and its wrapped key) never exposes any other version's
data key, and the provider's own root key -- the thing actually worth
protecting -- never leaves the provider at all.

This is a real, meaningful upgrade from a prior single-static-key
design (a `secrets_master_key` in this module's own config directly
encrypted every value) -- see `security/key_management.py`'s own
docstring for why that shape is now demoted to
`LocalStaticKeyManagementProvider`, an explicitly-flagged
not-a-real-KMS fallback rather than this module's only option.

This needs real I/O (the KMS/Vault round trip inside
`KeyManagementProvider`), so unlike before, `EnvelopeCipher` is no
longer a pure, I/O-free class -- `encrypt`/`decrypt` are now async.
"""
from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken

from secrets_and_credential_management.core.ports import KeyManagementProvider


class DecryptionError(Exception):
    def __init__(self) -> None:
        super().__init__("Failed to decrypt secret value -- wrong key or corrupted ciphertext")


def _fernet_for(data_key: bytes) -> Fernet:
    # Fernet's own key format is exactly this: a 32-byte key, url-safe-base64-encoded.
    # `data_key` is always 32 raw bytes (KeyManagementProvider's own contract), so this
    # is a pure format conversion, not a second key derivation step.
    return Fernet(base64.urlsafe_b64encode(data_key))


class EnvelopeCipher:
    def __init__(self, *, key_provider: KeyManagementProvider) -> None:
        self._key_provider = key_provider

    async def encrypt(self, plaintext: str) -> tuple[str, str]:
        """Returns `(ciphertext, wrapped_data_key)` -- both must be
        persisted together (`SecretVersionRecord`); neither is useful
        without the other."""
        data_key, wrapped_data_key = await self._key_provider.generate_data_key()
        ciphertext = _fernet_for(data_key).encrypt(plaintext.encode()).decode()
        return ciphertext, wrapped_data_key

    async def decrypt(self, *, ciphertext: str, wrapped_data_key: str) -> str:
        data_key = await self._key_provider.decrypt_data_key(wrapped_data_key)
        try:
            return _fernet_for(data_key).decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise DecryptionError from exc
