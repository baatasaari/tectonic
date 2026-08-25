"""Envelope Cipher (LLD §Level 1 "Encryption at rest"): the one tool
that actually keeps a stored secret from being a plaintext credential
list. Every value this module ever writes to Postgres passes through
`encrypt` first; `decrypt` only ever runs after a real, live
`authorize` check has already passed (see `core/secret_access_service.py`).

Real, standard, authenticated symmetric encryption (`Fernet` --
AES-128-CBC + HMAC, from the `cryptography` library) keyed by this
module's own `secrets_master_key` -- a completely different secret and
trust boundary from `security/jwt_auth.py`'s platform-wide
`TECTONIC_JWT_SHARED_SECRET`. Compromising one must never compromise
the other.

Pure, deterministic cryptography -- no I/O, so unlike this module's
real HTTP peer clients, `EnvelopeCipher` needs no fake for unit tests:
tests construct and use the real thing directly.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class DecryptionError(Exception):
    def __init__(self) -> None:
        super().__init__("Failed to decrypt secret value -- wrong key or corrupted ciphertext")


class EnvelopeCipher:
    def __init__(self, *, master_key: str) -> None:
        self._fernet = Fernet(master_key.encode())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise DecryptionError from exc
