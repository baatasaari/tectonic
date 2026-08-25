"""Abstract ports this module depends on: persistence, and the real
Auditability peer client the Authorization Service emits denials to.
"""
from __future__ import annotations

from typing import Any, Protocol

from identity_and_access.core.domain import (
    AuthDecisionRecord,
    IdentityRecord,
    IdentityStatus,
    RoleRecord,
)


class IdentityAccessRepository(Protocol):
    async def create_identity(self, record: IdentityRecord) -> IdentityRecord: ...

    async def get_identity(self, identity_id: str) -> IdentityRecord | None: ...

    async def update_identity(self, record: IdentityRecord) -> IdentityRecord: ...

    async def list_identities(
        self, *, tenant_id: str | None = None, status: IdentityStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[IdentityRecord], int]: ...

    async def create_role(self, record: RoleRecord) -> RoleRecord: ...

    async def get_role(self, name: str) -> RoleRecord | None: ...

    async def list_roles(self, *, limit: int = 50, offset: int = 0) -> tuple[list[RoleRecord], int]: ...

    async def create_auth_decision(self, record: AuthDecisionRecord) -> AuthDecisionRecord: ...

    async def list_auth_decisions(
        self, *, identity_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AuthDecisionRecord], int]: ...


class AuditabilityClient(Protocol):
    async def emit(self, event: dict[str, Any]) -> None:
        """Posts to Auditability's own real `POST /v1/auditability/events`.
        Never raises -- a down Auditability peer degrades the audit
        emission, it must never block the auth decision itself."""
        ...
