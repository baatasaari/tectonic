"""Abstract ports this module depends on: persistence, and the two real
platform-peer clients the Secret Access Service gates on / audits to.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from secrets_and_credential_management.core.domain import (
    SecretAccessRecord,
    SecretRecord,
    SecretStatus,
    SecretVersionRecord,
)


class SecretsRepository(Protocol):
    async def create_secret(self, record: SecretRecord) -> SecretRecord: ...

    async def get_secret(self, secret_id: str) -> SecretRecord | None: ...

    async def update_secret(self, record: SecretRecord) -> SecretRecord: ...

    async def list_secrets(
        self, *, tenant_id: str | None = None, namespace: str | None = None, status: SecretStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[SecretRecord], int]: ...

    async def list_due_for_rotation(
        self, *, tenant_id: str | None = None, at: datetime, limit: int = 50, offset: int = 0,
    ) -> tuple[list[SecretRecord], int]: ...

    async def create_version(self, record: SecretVersionRecord) -> SecretVersionRecord: ...

    async def get_latest_version(self, secret_id: str) -> SecretVersionRecord | None: ...

    async def create_access_record(self, record: SecretAccessRecord) -> SecretAccessRecord: ...

    async def list_access_records(
        self, *, secret_id: str, limit: int = 50, offset: int = 0,
    ) -> tuple[list[SecretAccessRecord], int]: ...

    async def count_active_and_overdue(self, *, tenant_id: str | None, at: datetime) -> tuple[int, int]:
        """`(total_active, overdue)` -- the two raw numbers
        `RotationService.compliance_rate` divides."""
        ...


class IdentityAccessClient(Protocol):
    async def authorize(self, *, token: str, required_scope: str) -> dict[str, Any]:
        """Calls Identity and Access's real `POST
        /v1/identity-access/authorize`. Returns at least `{"allowed":
        bool, "reason": str}`."""
        ...


class AuditabilityClient(Protocol):
    async def emit(self, event: dict[str, Any]) -> None:
        """Posts to Auditability's own real `POST /v1/auditability/events`.
        Never raises -- a down Auditability peer degrades the audit
        emission, it must never block the access or rotation decision
        itself."""
        ...
