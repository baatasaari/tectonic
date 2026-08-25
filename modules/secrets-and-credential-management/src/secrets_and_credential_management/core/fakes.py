"""In-memory fakes for unit tests (LLD "Deployability and testability
contract"). `EnvelopeCipher` needs no fake -- see its own docstring --
so only the repository and the two real platform-peer clients
(Identity and Access, Auditability) are faked here.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from secrets_and_credential_management.core.domain import (
    SecretAccessRecord,
    SecretRecord,
    SecretStatus,
    SecretVersionRecord,
)


class InMemorySecretsRepository:
    def __init__(self) -> None:
        self.secrets: dict[str, SecretRecord] = {}
        self.versions: dict[str, list[SecretVersionRecord]] = {}
        self.access_records: dict[str, list[SecretAccessRecord]] = {}

    async def create_secret(self, record: SecretRecord) -> SecretRecord:
        self.secrets[record.id] = record
        self.versions.setdefault(record.id, [])
        return record

    async def get_secret(self, secret_id: str) -> SecretRecord | None:
        return self.secrets.get(secret_id)

    async def update_secret(self, record: SecretRecord) -> SecretRecord:
        self.secrets[record.id] = record
        return record

    async def list_secrets(
        self, *, tenant_id: str | None = None, namespace: str | None = None, status: SecretStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[SecretRecord], int]:
        results = list(self.secrets.values())
        if tenant_id is not None:
            results = [s for s in results if s.tenant_id == tenant_id]
        if namespace is not None:
            results = [s for s in results if s.namespace == namespace]
        if status is not None:
            results = [s for s in results if s.status == status]
        results = sorted(results, key=lambda s: s.created_at)
        return results[offset:offset + limit], len(results)

    async def list_due_for_rotation(
        self, *, tenant_id: str | None = None, at: datetime, limit: int = 50, offset: int = 0,
    ) -> tuple[list[SecretRecord], int]:
        results = [
            s for s in self.secrets.values()
            if s.status == SecretStatus.ACTIVE and s.next_rotation_due_at <= at
        ]
        if tenant_id is not None:
            results = [s for s in results if s.tenant_id == tenant_id]
        results = sorted(results, key=lambda s: s.next_rotation_due_at)
        return results[offset:offset + limit], len(results)

    async def create_version(self, record: SecretVersionRecord) -> SecretVersionRecord:
        self.versions.setdefault(record.secret_id, []).append(record)
        return record

    async def get_latest_version(self, secret_id: str) -> SecretVersionRecord | None:
        versions = self.versions.get(secret_id) or []
        if not versions:
            return None
        return max(versions, key=lambda v: v.version)

    async def create_access_record(self, record: SecretAccessRecord) -> SecretAccessRecord:
        self.access_records.setdefault(record.secret_id, []).append(record)
        return record

    async def list_access_records(
        self, *, secret_id: str, limit: int = 50, offset: int = 0,
    ) -> tuple[list[SecretAccessRecord], int]:
        results = sorted(self.access_records.get(secret_id, []), key=lambda r: r.accessed_at, reverse=True)
        return results[offset:offset + limit], len(results)

    async def count_active_and_overdue(self, *, tenant_id: str | None, at: datetime) -> tuple[int, int]:
        results = [s for s in self.secrets.values() if s.status == SecretStatus.ACTIVE]
        if tenant_id is not None:
            results = [s for s in results if s.tenant_id == tenant_id]
        overdue = sum(1 for s in results if s.next_rotation_due_at <= at)
        return len(results), overdue


class StubIdentityAccessClient:
    """A caller-controlled stand-in for the real Identity and Access
    peer. Tests set `.allow`/`.reason` to script the zero-trust gate's
    verdict, or `.raise_error` to simulate the peer being down."""

    def __init__(self, *, allow: bool = True, reason: str = "ok", raise_error: bool = False) -> None:
        self.allow = allow
        self.reason = reason
        self.raise_error = raise_error
        self.calls: list[dict[str, Any]] = []

    async def authorize(self, *, token: str, required_scope: str) -> dict[str, Any]:
        if self.raise_error:
            raise RuntimeError("identity-and-access is down")
        self.calls.append({"token": token, "required_scope": required_scope})
        return {"allowed": self.allow, "reason": self.reason}


class StubAuditabilityClient:
    def __init__(self, *, raise_error: bool = False) -> None:
        self.events: list[dict[str, Any]] = []
        self._raise_error = raise_error

    async def emit(self, event: dict[str, Any]) -> None:
        if self._raise_error:
            raise RuntimeError("auditability is down")
        self.events.append(event)


def utcnow() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "InMemorySecretsRepository",
    "StubAuditabilityClient",
    "StubIdentityAccessClient",
]
