"""Authorization Service (LLD §2 sub-components, §Level 3 "The
zero-trust authorize check"): the one real gate any platform module can
call to turn a token plus a required scope into a live, auditable
allow/deny decision. The difference from a bare JWT check: the issuing
identity's *current* status is looked up live, right now, on every
call -- a revoked identity's outstanding tokens stop authorizing
immediately, not whenever they happen to expire.
"""
from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeVar

from identity_and_access.core.domain import (
    AuthDecisionRecord,
    AuthDecisionResult,
    IdentityStatus,
    new_id,
)
from identity_and_access.core.ports import AuditabilityClient, IdentityAccessRepository
from identity_and_access.security.token_signer import JWTTokenSigner, TokenVerificationError
from identity_and_access.telemetry.logging import get_logger
from identity_and_access.telemetry.metrics import (
    identity_access_auth_decisions_total,
    identity_access_unauthorized_attempts_total,
)

logger = get_logger(component="authorization_service")

T = TypeVar("T")


class AuthorizationService:
    def __init__(
        self, repository: IdentityAccessRepository, signer: JWTTokenSigner, auditability: AuditabilityClient,
    ) -> None:
        self._repository = repository
        self._signer = signer
        self._auditability = auditability

    @staticmethod
    async def _safe_call(call: Awaitable[T], *, default: T) -> T:
        try:
            return await call
        except Exception as exc:
            logger.warning("audit_emission_failed", error=str(exc))
            return default

    async def authorize(self, *, token: str, required_scope: str) -> AuthDecisionResult:
        try:
            claims = self._signer.verify(token)
        except TokenVerificationError as exc:
            return await self._record(
                tenant_id="unknown", identity_id="unknown", required_scope=required_scope,
                allowed=False, reason=f"invalid token: {exc.reason}",
            )

        identity_id = claims["sub"]
        tenant_id = claims["tenant_id"]
        token_scopes = claims["scopes"]

        # The zero-trust check: a valid, unexpired token signature is not enough. The
        # issuing identity's status is looked up live -- revoked (or deleted) since the
        # token was minted means an immediate deny, regardless of what the token itself
        # still claims or how long it has left before natural expiry.
        identity = await self._repository.get_identity(identity_id)
        if identity is None or identity.status != IdentityStatus.ACTIVE:
            return await self._record(
                tenant_id=tenant_id, identity_id=identity_id, required_scope=required_scope,
                allowed=False, reason="identity is not active",
            )

        if required_scope not in token_scopes:
            return await self._record(
                tenant_id=tenant_id, identity_id=identity_id, required_scope=required_scope,
                allowed=False, reason=f"missing scope: {required_scope}",
            )

        return await self._record(
            tenant_id=tenant_id, identity_id=identity_id, required_scope=required_scope, allowed=True, reason="ok",
        )

    async def _record(
        self, *, tenant_id: str, identity_id: str, required_scope: str, allowed: bool, reason: str,
    ) -> AuthDecisionResult:
        record = AuthDecisionRecord(
            id=new_id(), tenant_id=tenant_id, identity_id=identity_id, required_scope=required_scope,
            allowed=allowed, reason=reason,
        )
        await self._repository.create_auth_decision(record)

        identity_access_auth_decisions_total.labels(allowed=str(allowed)).inc()
        if not allowed:
            identity_access_unauthorized_attempts_total.labels(tenant_id=tenant_id, required_scope=required_scope).inc()
            logger.warning("unauthorized_attempt", tenant_id=tenant_id, identity_id=identity_id, reason=reason)
            await self._safe_call(
                self._auditability.emit({
                    "tenant_id": tenant_id,
                    "event_type": "identity_access.unauthorized_attempt",
                    "payload": {"identity_id": identity_id, "required_scope": required_scope, "reason": reason},
                }),
                default=None,
            )

        return AuthDecisionResult(allowed=allowed, reason=reason)
