"""In-memory fakes for unit tests (LLD "Deployability and testability
contract"). `sdk_codegen.generate_python_client` needs no fake -- see
its own docstring -- so only the repository and the four real
platform-peer clients are faked here.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sdk_and_developer_portal.core.domain import (
    DeveloperAccountRecord,
    DeveloperStatus,
    ModuleCatalogEntryRecord,
    SdkPackageRecord,
    new_id,
)


class InMemoryPortalRepository:
    def __init__(self) -> None:
        self.developers: dict[str, DeveloperAccountRecord] = {}
        self.catalog_entries: dict[str, ModuleCatalogEntryRecord] = {}
        self.sdk_packages: dict[str, SdkPackageRecord] = {}

    async def create_developer(self, record: DeveloperAccountRecord) -> DeveloperAccountRecord:
        self.developers[record.id] = record
        return record

    async def get_developer(self, developer_id: str) -> DeveloperAccountRecord | None:
        return self.developers.get(developer_id)

    async def update_developer(self, record: DeveloperAccountRecord) -> DeveloperAccountRecord:
        self.developers[record.id] = record
        return record

    async def list_developers(
        self, *, status: DeveloperStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[DeveloperAccountRecord], int]:
        results = list(self.developers.values())
        if status is not None:
            results = [d for d in results if d.status == status]
        results = sorted(results, key=lambda d: d.created_at)
        return results[offset:offset + limit], len(results)

    async def count_developers(self, *, status: DeveloperStatus | None = None) -> int:
        results = list(self.developers.values())
        if status is not None:
            results = [d for d in results if d.status == status]
        return len(results)

    async def list_all_developers(self) -> list[DeveloperAccountRecord]:
        return list(self.developers.values())

    async def upsert_catalog_entry(self, record: ModuleCatalogEntryRecord) -> ModuleCatalogEntryRecord:
        self.catalog_entries[record.module_name] = record
        return record

    async def get_catalog_entry(self, module_name: str) -> ModuleCatalogEntryRecord | None:
        return self.catalog_entries.get(module_name)

    async def list_catalog_entries(
        self, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ModuleCatalogEntryRecord], int]:
        results = sorted(self.catalog_entries.values(), key=lambda e: e.module_name)
        return results[offset:offset + limit], len(results)

    async def create_sdk_package(self, record: SdkPackageRecord) -> SdkPackageRecord:
        self.sdk_packages[record.id] = record
        return record

    async def get_sdk_package(self, package_id: str) -> SdkPackageRecord | None:
        return self.sdk_packages.get(package_id)

    async def get_latest_sdk_package(self, *, module_name: str, language: str) -> SdkPackageRecord | None:
        candidates = [
            p for p in self.sdk_packages.values() if p.module_name == module_name and p.language == language
        ]
        return max(candidates, key=lambda p: p.version) if candidates else None

    async def list_sdk_packages(
        self, *, module_name: str | None = None, language: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[SdkPackageRecord], int]:
        results = list(self.sdk_packages.values())
        if module_name is not None:
            results = [p for p in results if p.module_name == module_name]
        if language is not None:
            results = [p for p in results if p.language == language]
        results = sorted(results, key=lambda p: p.generated_at, reverse=True)
        return results[offset:offset + limit], len(results)


class StubIdentityAccessClient:
    def __init__(self, *, raise_on_register: bool = False, raise_on_revoke: bool = False) -> None:
        self.registered: list[dict[str, Any]] = []
        self.revoked: list[str] = []
        self.raise_on_register = raise_on_register
        self.raise_on_revoke = raise_on_revoke

    async def register_identity(self, *, name: str, type_: str, role_names: list[str]) -> str:
        if self.raise_on_register:
            raise RuntimeError("identity-and-access is down")
        identity_id = new_id()
        self.registered.append({"id": identity_id, "name": name, "type": type_, "role_names": role_names})
        return identity_id

    async def revoke_identity(self, identity_id: str) -> None:
        if self.raise_on_revoke:
            raise RuntimeError("identity-and-access is down")
        self.revoked.append(identity_id)

    async def issue_token(self, *, identity_id: str, requested_scopes: list[str] | None) -> dict[str, Any]:
        return {"token": f"token-for-{identity_id}", "granted_scopes": requested_scopes or []}


class StubMultiTenancyClient:
    def __init__(self, *, raise_error: bool = False) -> None:
        self.created: list[dict[str, Any]] = []
        self.raise_error = raise_error

    async def create_tenant(self, *, name: str, tier: str) -> str:
        if self.raise_error:
            raise RuntimeError("multi-tenancy is down")
        tenant_id = new_id()
        self.created.append({"id": tenant_id, "name": name, "tier": tier})
        return tenant_id


class StubAuditabilityClient:
    def __init__(self, *, events_by_tenant: dict[str, list[datetime]] | None = None) -> None:
        self._events_by_tenant = events_by_tenant or {}

    async def count_events(self, *, tenant_id: str) -> int:
        return len(self._events_by_tenant.get(tenant_id, []))

    async def get_event_occurred_at(self, *, tenant_id: str, offset: int) -> datetime:
        events = sorted(self._events_by_tenant.get(tenant_id, []), reverse=True)
        return events[offset]


class StubModuleSpecClient:
    def __init__(self, specs: dict[str, dict[str, Any]] | None = None, *, raise_for: set[str] | None = None) -> None:
        self._specs = specs or {}
        self._raise_for = raise_for or set()

    async def fetch_spec(self, *, base_url: str, audience: str) -> dict[str, Any]:
        if audience in self._raise_for:
            raise RuntimeError(f"{audience} is unreachable")
        return self._specs.get(audience, {"info": {"title": audience, "version": "0.1.0"}, "paths": {}})


__all__ = [
    "InMemoryPortalRepository",
    "StubAuditabilityClient",
    "StubIdentityAccessClient",
    "StubModuleSpecClient",
    "StubMultiTenancyClient",
]
