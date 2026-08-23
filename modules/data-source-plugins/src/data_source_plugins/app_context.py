"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from data_source_plugins.config import DataSourcePluginsSettings
from data_source_plugins.core.ports import SecretsClient, SourceConnectorRuntime


@dataclass
class AppContext:
    settings: DataSourcePluginsSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    connector_runtime: SourceConnectorRuntime
    secrets_client: SecretsClient
