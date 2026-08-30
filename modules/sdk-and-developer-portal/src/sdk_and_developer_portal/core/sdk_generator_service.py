"""SDK Generator Service (LLD §2 sub-components, §Level 3): turns a
catalogued module's real spec into a real, working client via
`sdk_codegen.py`'s pure generator. Regeneration is idempotent, keyed
off the spec's own content hash -- an unchanged spec returns the
existing package instead of manufacturing SDK churn.
"""
from __future__ import annotations

from sdk_and_developer_portal.core.domain import (
    SUPPORTED_SDK_LANGUAGES,
    SdkPackageNotFoundError,
    SdkPackageRecord,
    UnsupportedSdkLanguageError,
    new_id,
)
from sdk_and_developer_portal.core.module_catalog_service import ModuleCatalogService
from sdk_and_developer_portal.core.ports import PortalRepository
from sdk_and_developer_portal.core.sdk_codegen import generate_python_client
from sdk_and_developer_portal.telemetry.metrics import sdk_portal_sdk_generations_total


class SdkGeneratorService:
    def __init__(self, repository: PortalRepository, catalog: ModuleCatalogService) -> None:
        self._repository = repository
        self._catalog = catalog

    async def generate_sdk(self, *, module_name: str, language: str = "python") -> SdkPackageRecord:
        if language not in SUPPORTED_SDK_LANGUAGES:
            sdk_portal_sdk_generations_total.labels(outcome="failure").inc()
            raise UnsupportedSdkLanguageError(language)

        try:
            entry = await self._catalog.get(module_name)
        except Exception:
            sdk_portal_sdk_generations_total.labels(outcome="failure").inc()
            raise

        existing = await self._repository.get_latest_sdk_package(module_name=module_name, language=language)
        if existing is not None and existing.spec_hash == entry.spec_hash:
            sdk_portal_sdk_generations_total.labels(outcome="success").inc()
            return existing

        source_code = generate_python_client(module_name=module_name, base_url=entry.base_url, spec=entry.spec_json)
        next_version = (existing.version + 1) if existing is not None else 1

        package = await self._repository.create_sdk_package(SdkPackageRecord(
            id=new_id(), module_name=module_name, language=language, version=next_version,
            source_code=source_code, spec_hash=entry.spec_hash,
        ))
        sdk_portal_sdk_generations_total.labels(outcome="success").inc()
        return package

    async def get(self, package_id: str) -> SdkPackageRecord:
        package = await self._repository.get_sdk_package(package_id)
        if package is None:
            raise SdkPackageNotFoundError(package_id)
        return package

    async def list(
        self, *, module_name: str | None = None, language: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[SdkPackageRecord], int]:
        return await self._repository.list_sdk_packages(
            module_name=module_name, language=language, limit=limit, offset=offset,
        )
