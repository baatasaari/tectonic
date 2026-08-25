"""Developer Account Service (LLD §2 sub-components): registers a
developer as a REAL Identity and Access identity plus a REAL
Multi-tenancy sandbox tenant, and proxies sandbox token issuance --
this module never mints or stores a token itself.

Registration is a best-effort two-step provision: if tenant creation
fails after identity registration already succeeded, the identity is
left orphaned in Identity and Access for an operator to clean up
(this module does no saga-style rollback, the same modest scope every
other module in this platform keeps to for its own peer calls).
"""
from __future__ import annotations

from typing import Any

from sdk_and_developer_portal.core.domain import (
    DeveloperAccountRecord,
    DeveloperNotFoundError,
    DeveloperRevokedError,
    DeveloperStatus,
    InvalidTransitionError,
    is_legal_transition,
    new_id,
    now,
)
from sdk_and_developer_portal.core.ports import (
    IdentityAccessClient,
    MultiTenancyClient,
    PortalRepository,
)
from sdk_and_developer_portal.telemetry.metrics import sdk_portal_developers_registered_total


class DeveloperAccountService:
    def __init__(
        self, repository: PortalRepository, identity_access: IdentityAccessClient, multi_tenancy: MultiTenancyClient,
    ) -> None:
        self._repository = repository
        self._identity_access = identity_access
        self._multi_tenancy = multi_tenancy

    async def register(
        self, *, name: str, email: str, role_names: list[str] | None = None,
    ) -> DeveloperAccountRecord:
        identity_id = await self._identity_access.register_identity(
            name=name, type_="user", role_names=role_names or [],
        )
        # tier="sandbox" reuses Multi-tenancy's own real `tier` field as the queryable
        # signal that separates trial tenants from paying ones -- no second
        # sandbox-tracking system.
        tenant_id = await self._multi_tenancy.create_tenant(name=f"sandbox-{name}", tier="sandbox")

        record = await self._repository.create_developer(DeveloperAccountRecord(
            id=new_id(), name=name, email=email, tenant_id=tenant_id, identity_id=identity_id,
        ))
        sdk_portal_developers_registered_total.inc()
        return record

    async def get(self, developer_id: str) -> DeveloperAccountRecord:
        developer = await self._repository.get_developer(developer_id)
        if developer is None:
            raise DeveloperNotFoundError(developer_id)
        return developer

    async def list(
        self, *, status: DeveloperStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[DeveloperAccountRecord], int]:
        return await self._repository.list_developers(status=status, limit=limit, offset=offset)

    async def revoke(self, developer_id: str) -> DeveloperAccountRecord:
        developer = await self.get(developer_id)
        if not is_legal_transition(developer.status, DeveloperStatus.REVOKED):
            raise InvalidTransitionError(developer.status, DeveloperStatus.REVOKED)

        # The real peer is revoked first: local status must never claim a revocation the
        # peer itself doesn't yet reflect.
        await self._identity_access.revoke_identity(developer.identity_id)

        developer.status = DeveloperStatus.REVOKED
        developer.updated_at = now()
        return await self._repository.update_developer(developer)

    async def issue_sandbox_token(
        self, developer_id: str, *, requested_scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        developer = await self.get(developer_id)
        if developer.status != DeveloperStatus.ACTIVE:
            raise DeveloperRevokedError(developer_id)
        return await self._identity_access.issue_token(
            identity_id=developer.identity_id, requested_scopes=requested_scopes,
        )
