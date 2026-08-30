"""JWT Token Signer (LLD §Level 3 "The zero-trust authorize check"): the
one module-level tool that mints and verifies the fine-grained,
per-identity scoped tokens `TokenService`/`AuthorizationService` deal
in. Deliberately signed with this module's own `token_signing_secret`
-- a distinct key from `security/jwt_auth.py`'s platform-wide
`TECTONIC_JWT_SHARED_SECRET`. That secret protects the coarse,
module-to-module trust boundary (any module can call any other
module); this one protects the fine-grained, per-identity, zero-trust
boundary these tokens exist for. Compromising one must never
compromise the other.

Pure, deterministic cryptography -- no I/O, so unlike this module's
real HTTP peer clients, `JWTTokenSigner` needs no fake for unit tests:
tests construct and use the real thing directly.
"""
from __future__ import annotations

import time
from typing import Any

import jwt

ALGORITHM = "HS256"


class TokenVerificationError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Token verification failed: {reason}")
        self.reason = reason


class JWTTokenSigner:
    def __init__(self, *, signing_secret: str) -> None:
        self._signing_secret = signing_secret

    def mint(self, *, identity_id: str, tenant_id: str, scopes: list[str], ttl_seconds: int) -> str:
        now = int(time.time())
        payload = {
            "sub": identity_id, "tenant_id": tenant_id, "scopes": " ".join(scopes),
            "iat": now, "exp": now + ttl_seconds,
        }
        return jwt.encode(payload, self._signing_secret, algorithm=ALGORITHM)

    def verify(self, token: str) -> dict[str, Any]:
        try:
            claims = jwt.decode(token, self._signing_secret, algorithms=[ALGORITHM])
        except jwt.ExpiredSignatureError as exc:
            raise TokenVerificationError("token expired") from exc
        except jwt.PyJWTError as exc:
            raise TokenVerificationError(str(exc)) from exc
        claims["scopes"] = claims.get("scopes", "").split()
        return claims
