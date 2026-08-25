"""Secret Registry Service (LLD §2 sub-components): create, list, and
revoke secrets. Every plaintext value this service is ever handed is
encrypted via `EnvelopeCipher` before it touches the repository -- the
service itself never persists (or logs) a plaintext value.
"""
from __future__ import annotations

from datetime import timedelta

from secrets_and_credential_management.core.domain import (
    InvalidTransitionError,
    SecretNotFoundError,
    SecretRecord,
    SecretStatus,
    SecretVersionRecord,
    is_legal_transition,
    new_id,
    now,
)
from secrets_and_credential_management.core.ports import SecretsRepository
from secrets_and_credential_management.security.envelope_encryption import EnvelopeCipher


class SecretRegistryService:
    def __init__(self, repository: SecretsRepository, cipher: EnvelopeCipher) -> None:
        self._repository = repository
        self._cipher = cipher

    async def create_secret(
        self, *, tenant_id: str, namespace: str, key_name: str, value: str, rotation_interval_days: int = 90,
    ) -> SecretRecord:
        # SecretRecord's own default for next_rotation_due_at is a fixed 90 days -- it
        # knows nothing about the rotation_interval_days a caller passes here, so it must
        # be computed explicitly from the actual interval, not left at the dataclass default.
        created_at = now()
        secret = SecretRecord(
            id=new_id(), tenant_id=tenant_id, namespace=namespace, key_name=key_name,
            rotation_interval_days=rotation_interval_days,
            last_rotated_at=created_at,
            next_rotation_due_at=created_at + timedelta(days=rotation_interval_days),
            created_at=created_at, updated_at=created_at,
        )
        secret = await self._repository.create_secret(secret)
        await self._repository.create_version(SecretVersionRecord(
            id=new_id(), secret_id=secret.id, version=1, ciphertext=self._cipher.encrypt(value),
        ))
        return secret

    async def get_secret(self, secret_id: str) -> SecretRecord:
        secret = await self._repository.get_secret(secret_id)
        if secret is None:
            raise SecretNotFoundError(secret_id)
        return secret

    async def list_secrets(
        self, *, tenant_id: str | None = None, namespace: str | None = None, status: SecretStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[SecretRecord], int]:
        return await self._repository.list_secrets(
            tenant_id=tenant_id, namespace=namespace, status=status, limit=limit, offset=offset,
        )

    async def revoke_secret(self, secret_id: str) -> SecretRecord:
        secret = await self.get_secret(secret_id)
        if not is_legal_transition(secret.status, SecretStatus.REVOKED):
            raise InvalidTransitionError(secret.status, SecretStatus.REVOKED)
        secret.status = SecretStatus.REVOKED
        secret.updated_at = now()
        return await self._repository.update_secret(secret)
