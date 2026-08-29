"""`KeyManagementProvider` implementations (independent architecture
assessment: this module's envelope encryption previously had no real
managed-KMS backing at all -- one static `secrets_master_key` living in
this module's own config directly encrypted every value, meaning
compromising this module's config compromised every secret it ever
stored, with no external root-of-trust, no independent access control
on the key itself, and no key rotation story).

Two implementations behind the one `KeyManagementProvider` port
(`core/ports.py`), the same "swap the implementation, keep the
interface" shape this platform already uses for Qdrant/fastembed,
OIDC's real-vs-stub token verifier, etc.:

- `LocalStaticKeyManagementProvider`: wraps every fresh per-encrypt
  data key with a single static local Fernet key -- structurally the
  *previous* design, demoted to an explicitly-flagged zero-config
  local dev/test fallback. It is NOT a real managed KMS: the "root
  key" is still just a config value with no external audit trail, no
  independent revocation, no HSM backing. `main.py` logs a loud
  startup warning whenever this is what's actually wired in a running
  process -- the same posture `qdrant.embedded_in_memory` and
  `jwt_shared_secret_is_insecure_default` already take elsewhere in
  this platform for "the safe local default is not a safe production
  choice."
- `VaultTransitKeyManagementProvider`: a real HashiCorp Vault Transit
  secrets engine integration -- Vault's own `datakey`/`decrypt`
  endpoints generate and unwrap every data key this module ever uses,
  so the actual encryption root key lives in Vault, is never
  transmitted to this module in any form, and inherits Vault's own
  access control, audit logging, and key-rotation machinery for free.
  Plain `httpx` calls through `ResilientHTTPClient` (retry + circuit
  breaker, this module's standard outbound-peer shape), not the `hvac`
  SDK -- consistent with this platform's convention of small,
  hand-written adapters over heavy client libraries elsewhere
  (`security/jwt_auth.py`, Identity and Access's `oidc_verifier.py`).
  No live Vault server is reachable from this sandbox to integration-test
  against (the same "real client, mocked transport" constraint the
  OIDC verifier hit) -- `tests/unit/test_vault_key_management.py`
  verifies this class against a respx-mocked transport using Vault's
  real, documented request/response shapes; a genuine Vault dev server
  is the honest verification path this leaves for a real deployment
  (`vault server -dev` plus this provider pointed at it), not something
  fabricated here. AWS KMS/GCP KMS are the same shape behind the same
  port, unbuilt -- swapping one in means implementing this provider's
  two methods against that cloud's own API, nothing about the rest of
  this module changes.
"""
from __future__ import annotations

import base64
import os

import httpx
from cryptography.fernet import Fernet, InvalidToken

from secrets_and_credential_management.clients.resilience import ResilientHTTPClient

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


class KeyManagementError(Exception):
    """Raised for any failure unwrapping/generating a data key --
    wrong root key, a revoked key version, or the provider being
    unreachable. Callers (`EnvelopeCipher`) never need to know which
    provider-specific exception this was."""


class LocalStaticKeyManagementProvider:
    """NOT a real managed KMS -- see this file's module docstring.
    Zero-config, zero-network, deterministic: needs no fake for unit
    tests, the same "pure crypto needs no fake" precedent
    `JWTTokenSigner`/the old `EnvelopeCipher` already established."""

    def __init__(self, *, master_key: str) -> None:
        self._wrapping_fernet = Fernet(master_key.encode())

    async def generate_data_key(self) -> tuple[bytes, str]:
        data_key = os.urandom(32)
        wrapped = self._wrapping_fernet.encrypt(data_key).decode()
        return data_key, wrapped

    async def decrypt_data_key(self, wrapped_data_key: str) -> bytes:
        try:
            return self._wrapping_fernet.decrypt(wrapped_data_key.encode())
        except InvalidToken as exc:
            raise KeyManagementError("failed to unwrap data key -- wrong master key or corrupted value") from exc


class VaultTokenAuth(httpx.Auth):
    """Attaches Vault's own `X-Vault-Token` header to every outbound
    request -- Vault's auth model, not this platform's service JWT
    (Vault is an external secrets-management system, not a Tectonic
    peer module)."""

    def __init__(self, token: str) -> None:
        self._token = token

    def auth_flow(self, request: httpx.Request):
        request.headers["X-Vault-Token"] = self._token
        yield request


class VaultTransitKeyManagementProvider(ResilientHTTPClient):
    """Real HashiCorp Vault Transit secrets engine integration -- see
    this file's module docstring."""

    def __init__(
        self, vault_addr: str, client: httpx.AsyncClient | None = None, *,
        vault_token: str = "", key_name: str = "tectonic-secrets",
    ) -> None:
        super().__init__(
            vault_addr, client=client, timeout=_SHORT_TIMEOUT, breaker_name="vault-transit", fail_max=5,
            auth=VaultTokenAuth(vault_token),
        )
        self._key_name = key_name

    async def generate_data_key(self) -> tuple[bytes, str]:
        try:
            # bits=256 -> a 32-byte AES key, matching Fernet's own key size exactly.
            resp = await self._post(f"/v1/transit/datakey/plaintext/{self._key_name}", json={"bits": 256})
        except httpx.HTTPError as exc:
            raise KeyManagementError(f"Vault datakey generation failed: {exc}") from exc
        data = resp.json()["data"]
        return base64.b64decode(data["plaintext"]), data["ciphertext"]

    async def decrypt_data_key(self, wrapped_data_key: str) -> bytes:
        try:
            resp = await self._post(f"/v1/transit/decrypt/{self._key_name}", json={"ciphertext": wrapped_data_key})
        except httpx.HTTPError as exc:
            raise KeyManagementError(f"Vault data key unwrap failed: {exc}") from exc
        return base64.b64decode(resp.json()["data"]["plaintext"])
