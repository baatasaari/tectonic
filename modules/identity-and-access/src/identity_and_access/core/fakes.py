"""In-memory fakes for unit tests (LLD "Deployability and testability
contract"). `JWTTokenSigner` needs no fake -- see its own docstring --
so only the repository and the real Auditability peer client are
faked here.
"""
from __future__ import annotations

from typing import Any

from identity_and_access.core.domain import (
    AuthDecisionRecord,
    IdentityRecord,
    IdentityStatus,
    RoleRecord,
)


class InMemoryIdentityAccessRepository:
    def __init__(self) -> None:
        self.identities: dict[str, IdentityRecord] = {}
        self.roles: dict[str, RoleRecord] = {}
        self.auth_decisions: list[AuthDecisionRecord] = []

    async def create_identity(self, record: IdentityRecord) -> IdentityRecord:
        self.identities[record.id] = record
        return record

    async def get_identity(self, identity_id: str) -> IdentityRecord | None:
        return self.identities.get(identity_id)

    async def update_identity(self, record: IdentityRecord) -> IdentityRecord:
        self.identities[record.id] = record
        return record

    async def list_identities(
        self, *, tenant_id: str | None = None, status: IdentityStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[IdentityRecord], int]:
        results = list(self.identities.values())
        if tenant_id is not None:
            results = [i for i in results if i.tenant_id == tenant_id]
        if status is not None:
            results = [i for i in results if i.status == status]
        results = sorted(results, key=lambda i: i.created_at)
        return results[offset:offset + limit], len(results)

    async def create_role(self, record: RoleRecord) -> RoleRecord:
        self.roles[record.name] = record
        return record

    async def get_role(self, name: str) -> RoleRecord | None:
        return self.roles.get(name)

    async def list_roles(self, *, limit: int = 50, offset: int = 0) -> tuple[list[RoleRecord], int]:
        results = sorted(self.roles.values(), key=lambda r: r.created_at)
        return results[offset:offset + limit], len(results)

    async def create_auth_decision(self, record: AuthDecisionRecord) -> AuthDecisionRecord:
        self.auth_decisions.append(record)
        return record

    async def list_auth_decisions(
        self, *, identity_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AuthDecisionRecord], int]:
        results = list(self.auth_decisions)
        if identity_id is not None:
            results = [d for d in results if d.identity_id == identity_id]
        results = sorted(results, key=lambda d: d.checked_at, reverse=True)
        return results[offset:offset + limit], len(results)


class StubAuditabilityClient:
    def __init__(self, *, raise_error: bool = False) -> None:
        self.events: list[dict[str, Any]] = []
        self._raise_error = raise_error

    async def emit(self, event: dict[str, Any]) -> None:
        if self._raise_error:
            raise RuntimeError("auditability is down")
        self.events.append(event)


__all__ = ["InMemoryIdentityAccessRepository", "StubAuditabilityClient"]
