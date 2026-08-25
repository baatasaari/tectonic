"""Module Catalog Service (LLD §2 sub-components): syncs every
configured peer module's real, live `GET /openapi.json` into a local,
queryable catalogue. One unreachable peer never blocks syncing the
rest -- it's skipped and logged, the same graceful-degradation shape
this platform's other cross-peer fan-outs already use.
"""
from __future__ import annotations

from sdk_and_developer_portal.config import CatalogTargetConfig
from sdk_and_developer_portal.core.domain import (
    ModuleCatalogEntryNotFoundError,
    ModuleCatalogEntryRecord,
    spec_hash,
)
from sdk_and_developer_portal.core.ports import ModuleSpecClient, PortalRepository
from sdk_and_developer_portal.telemetry.logging import get_logger

logger = get_logger(component="module_catalog_service")


class ModuleCatalogService:
    def __init__(self, repository: PortalRepository, module_spec: ModuleSpecClient) -> None:
        self._repository = repository
        self._module_spec = module_spec

    async def sync_catalog(self, targets: list[CatalogTargetConfig]) -> list[ModuleCatalogEntryRecord]:
        synced: list[ModuleCatalogEntryRecord] = []
        for target in targets:
            try:
                spec = await self._module_spec.fetch_spec(base_url=target.base_url, audience=target.name)
            except Exception as exc:
                logger.warning("catalog_sync_target_unreachable", module_name=target.name, error=str(exc))
                continue

            info = spec.get("info", {})
            entry = ModuleCatalogEntryRecord(
                module_name=target.name, base_url=target.base_url,
                title=info.get("title", target.name), version=str(info.get("version", "unknown")),
                path_count=len(spec.get("paths", {})), spec_json=spec, spec_hash=spec_hash(spec),
            )
            synced.append(await self._repository.upsert_catalog_entry(entry))

        return synced

    async def get(self, module_name: str) -> ModuleCatalogEntryRecord:
        entry = await self._repository.get_catalog_entry(module_name)
        if entry is None:
            raise ModuleCatalogEntryNotFoundError(module_name)
        return entry

    async def list(
        self, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ModuleCatalogEntryRecord], int]:
        return await self._repository.list_catalog_entries(limit=limit, offset=offset)
