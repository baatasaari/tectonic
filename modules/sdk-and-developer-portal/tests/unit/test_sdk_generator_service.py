"""Tests for core/sdk_generator_service.py -- spec-hash-keyed
idempotent generation."""
from __future__ import annotations

import pytest

from sdk_and_developer_portal.config import CatalogTargetConfig
from sdk_and_developer_portal.core.domain import (
    ModuleCatalogEntryNotFoundError,
    UnsupportedSdkLanguageError,
)
from sdk_and_developer_portal.core.fakes import StubModuleSpecClient

SPEC_V1 = {"info": {"title": "Auditability", "version": "1.0.0"}, "paths": {"/a": {"get": {"operationId": "a"}}}}
SPEC_V2 = {
    "info": {"title": "Auditability", "version": "1.1.0"},
    "paths": {"/a": {"get": {"operationId": "a"}}, "/b": {"get": {"operationId": "b"}}},
}


async def test_generate_sdk_produces_a_real_client(harness_factory):
    module_spec = StubModuleSpecClient({"auditability": SPEC_V1})
    h = harness_factory(module_spec=module_spec)
    await h.catalog_service.sync_catalog([CatalogTargetConfig(name="auditability", base_url="http://x")])

    package = await h.sdk_service.generate_sdk(module_name="auditability", language="python")

    assert package.version == 1
    assert "def a(self, **kwargs)" in package.source_code


async def test_generate_sdk_raises_when_module_not_catalogued(harness):
    with pytest.raises(ModuleCatalogEntryNotFoundError):
        await harness.sdk_service.generate_sdk(module_name="does-not-exist")


async def test_generate_sdk_rejects_an_unsupported_language(harness_factory):
    module_spec = StubModuleSpecClient({"auditability": SPEC_V1})
    h = harness_factory(module_spec=module_spec)
    await h.catalog_service.sync_catalog([CatalogTargetConfig(name="auditability", base_url="http://x")])

    with pytest.raises(UnsupportedSdkLanguageError):
        await h.sdk_service.generate_sdk(module_name="auditability", language="rust")


async def test_regenerating_against_an_unchanged_spec_returns_the_same_package(harness_factory):
    module_spec = StubModuleSpecClient({"auditability": SPEC_V1})
    h = harness_factory(module_spec=module_spec)
    await h.catalog_service.sync_catalog([CatalogTargetConfig(name="auditability", base_url="http://x")])

    first = await h.sdk_service.generate_sdk(module_name="auditability")
    second = await h.sdk_service.generate_sdk(module_name="auditability")

    assert first.id == second.id
    assert second.version == 1


async def test_regenerating_after_the_spec_changes_produces_a_new_version(harness_factory):
    module_spec = StubModuleSpecClient({"auditability": SPEC_V1})
    h = harness_factory(module_spec=module_spec)
    await h.catalog_service.sync_catalog([CatalogTargetConfig(name="auditability", base_url="http://x")])
    first = await h.sdk_service.generate_sdk(module_name="auditability")

    module_spec._specs["auditability"] = SPEC_V2
    await h.catalog_service.sync_catalog([CatalogTargetConfig(name="auditability", base_url="http://x")])
    second = await h.sdk_service.generate_sdk(module_name="auditability")

    assert second.id != first.id
    assert second.version == 2
    assert "def b(self, **kwargs)" in second.source_code
