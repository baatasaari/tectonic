from __future__ import annotations

import pytest

from data_source_plugins.config import DriftConfig, QualityConfig
from data_source_plugins.core.domain import ConnectorConfigRecord, new_id
from data_source_plugins.core.fakes import (
    InMemoryConnectorRepository,
    StubSecretsClient,
    StubSourceConnectorRuntime,
)
from data_source_plugins.core.sync_service import SyncService


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryConnectorRepository()
        self.connector_runtime = kwargs.get("connector_runtime") or StubSourceConnectorRuntime()
        self.secrets_client = kwargs.get("secrets_client") or StubSecretsClient()
        self.drift_config = kwargs.get("drift_config") or DriftConfig()
        self.quality_config = kwargs.get("quality_config") or QualityConfig()

        self.service = SyncService(
            self.repository, self.connector_runtime, self.secrets_client, self.drift_config, self.quality_config,
        )

    async def seed_connector(self, tenant_id: str = "tenant-a", source_type: str = "postgres") -> ConnectorConfigRecord:
        record = ConnectorConfigRecord(
            id=new_id(), tenant_id=tenant_id, source_type=source_type,
            connection_config={"host": "db.example.com"}, secrets_ref="secret-ref-1",
        )
        return await self.repository.create_connector(record)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
