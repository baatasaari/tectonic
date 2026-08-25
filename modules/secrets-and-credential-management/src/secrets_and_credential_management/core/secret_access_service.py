"""Secret Access Service (LLD §2 sub-components, §Level 3 "The
zero-trust-gated retrieval path"): the one path any caller has to get a
secret's plaintext value back. Nothing short-circuits the gate --
retrieval never returns a value without a real, live "allowed" verdict
from Identity and Access's own zero-trust `authorize` check (scoped
`secret:{tenant_id}:{namespace}:read`), and every attempt -- allowed or
denied -- is dual-recorded: a local `SecretAccessRecord` (always) and a
real Auditability event (best-effort; a down Auditability degrades the
audit trail, it must never block the decision itself).
"""
from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeVar

from secrets_and_credential_management.core.domain import (
    SecretAccessRecord,
    SecretAccessResult,
    SecretStatus,
    new_id,
)
from secrets_and_credential_management.core.ports import (
    AuditabilityClient,
    IdentityAccessClient,
    SecretsRepository,
)
from secrets_and_credential_management.security.envelope_encryption import (
    DecryptionError,
    EnvelopeCipher,
)
from secrets_and_credential_management.telemetry.logging import get_logger
from secrets_and_credential_management.telemetry.metrics import secrets_access_total

logger = get_logger(component="secret_access_service")

T = TypeVar("T")


class SecretAccessService:
    def __init__(
        self, repository: SecretsRepository, cipher: EnvelopeCipher,
        identity_access: IdentityAccessClient, auditability: AuditabilityClient,
    ) -> None:
        self._repository = repository
        self._cipher = cipher
        self._identity_access = identity_access
        self._auditability = auditability

    @staticmethod
    async def _safe_call(call: Awaitable[T], *, default: T) -> T:
        try:
            return await call
        except Exception as exc:
            logger.warning("audit_emission_failed", error=str(exc))
            return default

    async def retrieve(self, *, secret_id: str, token: str) -> SecretAccessResult:
        secret = await self._repository.get_secret(secret_id)
        if secret is None:
            return await self._record(
                secret_id=secret_id, tenant_id="unknown", allowed=False, reason="secret not found",
            )

        if secret.status != SecretStatus.ACTIVE:
            return await self._record(
                secret_id=secret.id, tenant_id=secret.tenant_id, allowed=False, reason="secret is revoked",
            )

        required_scope = f"secret:{secret.tenant_id}:{secret.namespace}:read"
        try:
            decision = await self._identity_access.authorize(token=token, required_scope=required_scope)
        except Exception as exc:
            logger.warning("identity_access_call_failed", secret_id=secret.id, error=str(exc))
            return await self._record(
                secret_id=secret.id, tenant_id=secret.tenant_id, allowed=False,
                reason="identity-and-access is unavailable",
            )

        if not decision.get("allowed", False):
            reason = decision.get("reason", "denied")
            return await self._record(secret_id=secret.id, tenant_id=secret.tenant_id, allowed=False, reason=reason)

        version = await self._repository.get_latest_version(secret.id)
        if version is None:
            return await self._record(
                secret_id=secret.id, tenant_id=secret.tenant_id, allowed=False, reason="no version stored",
            )

        try:
            value = self._cipher.decrypt(version.ciphertext)
        except DecryptionError:
            logger.warning("decryption_failed", secret_id=secret.id)
            return await self._record(
                secret_id=secret.id, tenant_id=secret.tenant_id, allowed=False, reason="decryption failed",
            )

        await self._record(secret_id=secret.id, tenant_id=secret.tenant_id, allowed=True, reason="ok")
        return SecretAccessResult(allowed=True, reason="ok", value=value)

    async def _record(self, *, secret_id: str, tenant_id: str, allowed: bool, reason: str) -> SecretAccessResult:
        record = SecretAccessRecord(id=new_id(), secret_id=secret_id, tenant_id=tenant_id, allowed=allowed, reason=reason)
        await self._repository.create_access_record(record)

        secrets_access_total.labels(allowed=str(allowed)).inc()
        if not allowed:
            logger.warning("secret_access_denied", secret_id=secret_id, tenant_id=tenant_id, reason=reason)

        await self._safe_call(
            self._auditability.emit({
                "tenant_id": tenant_id,
                "event_type": "secrets.access_attempt" if allowed else "secrets.access_denied",
                "payload": {"secret_id": secret_id, "allowed": allowed, "reason": reason},
            }),
            default=None,
        )

        return SecretAccessResult(allowed=allowed, reason=reason)
