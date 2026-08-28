"""Tests for main.py's build_app_context -- specifically the fix for the
independent architecture assessment's §10 Vector DB finding ("in-memory
Qdrant is the default", "migration state is in memory"). Neither
AsyncQdrantClient nor create_async_engine connects eagerly on
construction, so this can run with no real Qdrant or Postgres reachable
-- it's asserting how the client/repository get *built*, not exercising
a live connection (that's the integration tier's job).
"""
from __future__ import annotations

from qdrant_client import AsyncQdrantClient

import vector_db.main as main_module
from vector_db.config import QdrantConfig, VectorDbSettings
from vector_db.db.repository import SQLAlchemyMigrationRepository


async def _teardown(ctx):
    await ctx.qdrant.close()
    await ctx.engine.dispose()


async def test_the_default_config_never_falls_back_to_an_in_memory_client():
    settings = VectorDbSettings()

    assert settings.qdrant.embedded_in_memory is False
    assert settings.qdrant.url  # a real, non-empty default -- never None

    ctx = main_module.build_app_context(settings)
    try:
        assert isinstance(ctx.qdrant, AsyncQdrantClient)
    finally:
        await _teardown(ctx)


async def test_embedded_in_memory_true_logs_a_loud_warning(monkeypatch):
    warnings: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        main_module.logger, "warning", lambda event, **kw: warnings.append((event, kw)),
    )
    settings = VectorDbSettings(qdrant=QdrantConfig(embedded_in_memory=True))

    ctx = main_module.build_app_context(settings)
    try:
        pass
    finally:
        await _teardown(ctx)

    assert any(event == "qdrant_embedded_in_memory_mode" for event, _ in warnings)


async def test_the_default_config_does_not_log_the_in_memory_warning(monkeypatch):
    warnings: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        main_module.logger, "warning", lambda event, **kw: warnings.append((event, kw)),
    )
    settings = VectorDbSettings()

    ctx = main_module.build_app_context(settings)
    try:
        pass
    finally:
        await _teardown(ctx)

    assert not any(event == "qdrant_embedded_in_memory_mode" for event, _ in warnings)


async def test_an_explicit_qdrant_client_override_is_used_verbatim_and_skips_the_warning(monkeypatch):
    warnings: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        main_module.logger, "warning", lambda event, **kw: warnings.append((event, kw)),
    )
    settings = VectorDbSettings(qdrant=QdrantConfig(embedded_in_memory=True))
    injected = AsyncQdrantClient(location=":memory:")

    ctx = main_module.build_app_context(settings, qdrant_client=injected)
    try:
        assert ctx.qdrant is injected
    finally:
        await _teardown(ctx)

    # An explicit override always wins -- and is never itself the trigger for the
    # warning; only settings.qdrant.embedded_in_memory driving the *default*
    # construction path is (this test still sets it true above to prove the override
    # takes priority over it, not because the override cares about that field at all).
    assert not any(event == "qdrant_embedded_in_memory_mode" for event, _ in warnings)


async def test_migration_repository_is_always_the_real_postgres_backed_one():
    for embedded_in_memory in (True, False):
        settings = VectorDbSettings(qdrant=QdrantConfig(embedded_in_memory=embedded_in_memory))
        ctx = main_module.build_app_context(settings)
        try:
            assert isinstance(ctx.migration_repository, SQLAlchemyMigrationRepository)
        finally:
            await _teardown(ctx)
