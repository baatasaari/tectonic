"""Rotation Service (LLD §2 sub-components, §Level 3 "Rotation
compliance"): rotates a secret's value, tells a caller which secrets
are overdue, and computes the platform's one real compliance Gauge.

`rotate` is the boundary the LLD documents explicitly: this service
only records that a new value now exists (a new encrypted version,
`last_rotated_at`/`next_rotation_due_at` refreshed) -- actually turning
over the credential at the third-party system of record (a database
password, a cloud IAM key) is the caller's job, not this module's.
`list_due_for_rotation` is what a scheduler polls to know what needs
that real-world rotation done.
"""
from __future__ import annotations

from datetime import timedelta

from secrets_and_credential_management.core.domain import (
    ComplianceReport,
    SecretNotFoundError,
    SecretRecord,
    SecretRevokedError,
    SecretStatus,
    SecretVersionRecord,
    new_id,
    now,
)
from secrets_and_credential_management.core.ports import SecretsRepository
from secrets_and_credential_management.security.envelope_encryption import EnvelopeCipher
from secrets_and_credential_management.telemetry.metrics import (
    secrets_rotation_compliance_rate,
    secrets_rotations_total,
)


class RotationService:
    def __init__(self, repository: SecretsRepository, cipher: EnvelopeCipher) -> None:
        self._repository = repository
        self._cipher = cipher

    async def rotate(self, *, secret_id: str, new_value: str) -> SecretRecord:
        secret = await self._repository.get_secret(secret_id)
        if secret is None:
            raise SecretNotFoundError(secret_id)
        if secret.status != SecretStatus.ACTIVE:
            raise SecretRevokedError(secret_id)

        next_version = secret.current_version + 1
        ciphertext, wrapped_data_key = await self._cipher.encrypt(new_value)
        await self._repository.create_version(SecretVersionRecord(
            id=new_id(), secret_id=secret.id, version=next_version, ciphertext=ciphertext,
            wrapped_data_key=wrapped_data_key,
        ))

        rotated_at = now()
        secret.current_version = next_version
        secret.last_rotated_at = rotated_at
        secret.next_rotation_due_at = rotated_at + timedelta(days=secret.rotation_interval_days)
        secret.updated_at = rotated_at
        secret = await self._repository.update_secret(secret)

        secrets_rotations_total.labels(tenant_id=secret.tenant_id).inc()
        return secret

    async def list_due_for_rotation(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[SecretRecord], int]:
        return await self._repository.list_due_for_rotation(tenant_id=tenant_id, at=now(), limit=limit, offset=offset)

    async def compliance_rate(self, *, tenant_id: str | None = None) -> ComplianceReport:
        total_active, overdue = await self._repository.count_active_and_overdue(tenant_id=tenant_id, at=now())
        # Insufficient-data-over-fabrication: with zero active secrets there is nothing
        # to be compliant or non-compliant about -- report `None`, never a fabricated 1.0.
        rate = None if total_active == 0 else (total_active - overdue) / total_active
        if rate is not None:
            secrets_rotation_compliance_rate.labels(tenant_id=tenant_id or "all").set(rate)
        return ComplianceReport(tenant_id=tenant_id, total_active=total_active, overdue=overdue, compliance_rate=rate)
