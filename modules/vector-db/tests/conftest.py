from __future__ import annotations

import pytest
from qdrant_client import AsyncQdrantClient

from vector_db.config import IsolationConfig, QueryConfig
from vector_db.core.fakes import (
    InMemoryMigrationRepository,
    StubEmbeddingProvider,
    StubMultiTenancyQuotaClient,
)
from vector_db.core.migration_manager import MigrationManager
from vector_db.core.vector_service import VectorService


class Harness:
    def __init__(self, **kwargs):
        self.client = AsyncQdrantClient(location=":memory:")
        self.embeddings = kwargs.get("embeddings") or StubEmbeddingProvider(dimension=8)
        self.migration_repository = InMemoryMigrationRepository()
        self.isolation = kwargs.get("isolation") or IsolationConfig()
        self.query_config = kwargs.get("query_config") or QueryConfig()
        self.base_alias = kwargs.get("base_alias") or "vector_db_points"
        self.multi_tenancy = kwargs.get("multi_tenancy") or StubMultiTenancyQuotaClient()

        self.vector_service = VectorService(
            self.client, self.embeddings, self.base_alias, self.isolation, self.query_config,
            "text-embedding-3-small", multi_tenancy=self.multi_tenancy,
        )
        self.migration_manager = MigrationManager(
            self.client, self.embeddings, self.migration_repository, self.base_alias,
            self.isolation.tenancy_model, kwargs.get("batch_size", 2), kwargs.get("verification_sample_rate", 0.5),
        )


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
