"""Tests for core/module_catalog_service.py -- syncs real peer specs
into the catalogue; one unreachable peer never blocks the rest."""
from __future__ import annotations

import pytest

from sdk_and_developer_portal.config import CatalogTargetConfig
from sdk_and_developer_portal.core.domain import ModuleCatalogEntryNotFoundError
from sdk_and_developer_portal.core.fakes import StubModuleSpecClient

SPEC = {"info": {"title": "Auditability", "version": "1.2.3"}, "paths": {"/a": {}, "/b": {}}}


async def test_sync_catalog_upserts_an_entry_per_target(harness_factory):
    module_spec = StubModuleSpecClient({"auditability": SPEC})
    h = harness_factory(module_spec=module_spec)
    targets = [CatalogTargetConfig(name="auditability", base_url="http://auditability:8090")]

    entries = await h.catalog_service.sync_catalog(targets)

    assert len(entries) == 1
    assert entries[0].module_name == "auditability"
    assert entries[0].title == "Auditability"
    assert entries[0].version == "1.2.3"
    assert entries[0].path_count == 2


async def test_sync_catalog_skips_an_unreachable_target_without_blocking_the_rest(harness_factory):
    module_spec = StubModuleSpecClient({"auditability": SPEC}, raise_for={"identity-and-access"})
    h = harness_factory(module_spec=module_spec)
    targets = [
        CatalogTargetConfig(name="identity-and-access", base_url="http://identity-and-access:8110"),
        CatalogTargetConfig(name="auditability", base_url="http://auditability:8090"),
    ]

    entries = await h.catalog_service.sync_catalog(targets)

    assert len(entries) == 1
    assert entries[0].module_name == "auditability"


async def test_get_raises_not_found(harness):
    with pytest.raises(ModuleCatalogEntryNotFoundError):
        await harness.catalog_service.get("does-not-exist")


async def test_list_returns_synced_entries(harness_factory):
    module_spec = StubModuleSpecClient({"auditability": SPEC})
    h = harness_factory(module_spec=module_spec)
    await h.catalog_service.sync_catalog([CatalogTargetConfig(name="auditability", base_url="http://x")])

    entries, total = await h.catalog_service.list()

    assert total == 1
    assert entries[0].module_name == "auditability"
