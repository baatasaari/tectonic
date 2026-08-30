"""Real OIDC ID token verification: fetches a provider's JWKS over HTTP
(cached per provider, since a JWKS document changes rarely and every
federated login would otherwise cost a network round trip), matches the
token's `kid` to a key, and verifies signature/issuer/audience via
PyJWT. This is the one piece of `core/oidc_federation_service.py` that
does real I/O and real asymmetric cryptography, so -- consistent with
this platform's usual split -- it lives behind the `OidcTokenVerifier`
port and gets a pure `StubOidcTokenVerifier` fake for business-logic
unit tests (core/fakes.py); `HTTPOidcTokenVerifier` itself is exercised
by a real end-to-end test that signs a token with a real RSA keypair and
serves it from a respx-mocked JWKS endpoint (real client, mocked
transport -- this platform's standard testing shape for outbound HTTP),
never a hand-rolled/skipped verification path.

RS256 (and other asymmetric algorithms) needs the `cryptography` package
installed alongside `pyjwt` -- `pyjwt`'s own HS256-only mode (used by
`security/jwt_auth.py` and `security/token_signer.py` elsewhere in this
module) doesn't require it, so it wasn't previously a dependency here.
"""
from __future__ import annotations

import time
from typing import Any

import httpx
import jwt

from identity_and_access.core.domain import FederationError, IdentityProviderRecord

_JWKS_CACHE_TTL_SECONDS = 300


class HTTPOidcTokenVerifier:
    def __init__(self, *, client: httpx.AsyncClient, jwks_cache_ttl_seconds: int = _JWKS_CACHE_TTL_SECONDS) -> None:
        self._client = client
        self._cache_ttl = jwks_cache_ttl_seconds
        self._jwks_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    async def _fetch_jwks(self, jwks_uri: str) -> list[dict[str, Any]]:
        cached = self._jwks_cache.get(jwks_uri)
        now = time.monotonic()
        if cached is not None and now - cached[0] < self._cache_ttl:
            return cached[1]

        try:
            response = await self._client.get(jwks_uri)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise FederationError(f"failed to fetch JWKS from {jwks_uri}: {exc}") from exc

        keys = response.json().get("keys", [])
        self._jwks_cache[jwks_uri] = (now, keys)
        return keys

    async def verify(self, *, id_token: str, provider: IdentityProviderRecord) -> dict[str, Any]:
        if not provider.jwks_uri:
            raise FederationError(f"identity provider {provider.id} has no jwks_uri configured")

        try:
            header = jwt.get_unverified_header(id_token)
        except jwt.PyJWTError as exc:
            raise FederationError(f"malformed id_token: {exc}") from exc

        kid = header.get("kid")
        keys = await self._fetch_jwks(provider.jwks_uri)
        matching = [k for k in keys if kid is None or k.get("kid") == kid]
        if not matching:
            raise FederationError(f"no matching JWKS key for kid={kid!r} at {provider.jwks_uri}")

        last_error: Exception | None = None
        for jwk in matching:
            try:
                public_key = jwt.PyJWK.from_dict(jwk).key
                claims = jwt.decode(
                    id_token, public_key, algorithms=[jwk.get("alg", "RS256")],
                    issuer=provider.issuer, audience=provider.client_id or None,
                    options={"require": ["exp", "iat", "sub"]},
                )
                return claims
            except jwt.PyJWTError as exc:
                last_error = exc
                continue

        raise FederationError(f"id_token verification failed: {last_error}")
