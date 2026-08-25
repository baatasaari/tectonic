"""Abstract ports this module depends on: persistence, and the four
real platform-peer clients this module composes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from sdk_and_developer_portal.core.domain import (
    DeveloperAccountRecord,
    DeveloperStatus,
    ModuleCatalogEntryRecord,
    SdkPackageRecord,
)


class PortalRepository(Protocol):
    async def create_developer(self, record: DeveloperAccountRecord) -> DeveloperAccountRecord: ...

    async def get_developer(self, developer_id: str) -> DeveloperAccountRecord | None: ...

    async def update_developer(self, record: DeveloperAccountRecord) -> DeveloperAccountRecord: ...

    async def list_developers(
        self, *, status: DeveloperStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[DeveloperAccountRecord], int]: ...

    async def count_developers(self, *, status: DeveloperStatus | None = None) -> int: ...

    async def list_all_developers(self) -> list[DeveloperAccountRecord]:
        """Unpaginated -- used only by `AdoptionMetricsService.adoption_rate`'s
        own aggregate computation, never exposed as a public listing endpoint."""
        ...

    async def upsert_catalog_entry(self, record: ModuleCatalogEntryRecord) -> ModuleCatalogEntryRecord: ...

    async def get_catalog_entry(self, module_name: str) -> ModuleCatalogEntryRecord | None: ...

    async def list_catalog_entries(
        self, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ModuleCatalogEntryRecord], int]: ...

    async def create_sdk_package(self, record: SdkPackageRecord) -> SdkPackageRecord: ...

    async def get_sdk_package(self, package_id: str) -> SdkPackageRecord | None: ...

    async def get_latest_sdk_package(self, *, module_name: str, language: str) -> SdkPackageRecord | None: ...

    async def list_sdk_packages(
        self, *, module_name: str | None = None, language: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[SdkPackageRecord], int]: ...


class IdentityAccessClient(Protocol):
    async def register_identity(self, *, name: str, type_: str, role_names: list[str]) -> str:
        """Calls Identity and Access's real `POST /v1/identity-access/identities`;
        returns the new identity's `id`."""
        ...

    async def revoke_identity(self, identity_id: str) -> None:
        """Calls Identity and Access's real `POST
        /v1/identity-access/identities/{id}/revoke`."""
        ...

    async def issue_token(self, *, identity_id: str, requested_scopes: list[str] | None) -> dict[str, Any]:
        """Calls Identity and Access's real `POST /v1/identity-access/tokens`;
        returns `{"token": str, "granted_scopes": list[str]}`."""
        ...


class MultiTenancyClient(Protocol):
    async def create_tenant(self, *, name: str, tier: str) -> str:
        """Calls Multi-tenancy's real `POST /v1/multi-tenancy/tenants`;
        returns the new tenant's `id`."""
        ...


class AuditabilityClient(Protocol):
    async def count_events(self, *, tenant_id: str) -> int:
        """Calls Auditability's real `GET /v1/auditability/events`
        (`limit=1`) and returns the `total` it reports."""
        ...

    async def get_event_occurred_at(self, *, tenant_id: str, offset: int) -> datetime:
        """Calls Auditability's real `GET /v1/auditability/events`
        (`limit=1`, this `offset`) and returns that one event's
        `occurred_at`."""
        ...


class ModuleSpecClient(Protocol):
    async def fetch_spec(self, *, base_url: str, audience: str) -> dict[str, Any]:
        """Calls a peer module's own real, live `GET /openapi.json`
        (behind that peer's own `ServiceAuthMiddleware`) and returns
        the parsed spec."""
        ...
