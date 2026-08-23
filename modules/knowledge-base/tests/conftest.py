from __future__ import annotations

import pytest

from knowledge_base.config import ChunkingConfig, StalenessConfig
from knowledge_base.core.fakes import (
    InMemoryBlobStorage,
    InMemoryKnowledgeBaseRepository,
    StubGraphDBClient,
    StubVectorDBClient,
)
from knowledge_base.core.ingestion_service import IngestionService


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryKnowledgeBaseRepository()
        self.blob_storage = InMemoryBlobStorage()
        self.vector_db = kwargs.get("vector_db") or StubVectorDBClient()
        self.graph_db = kwargs.get("graph_db") or StubGraphDBClient()
        self.chunking_config = kwargs.get("chunking_config") or ChunkingConfig()
        self.staleness_config = kwargs.get("staleness_config") or StalenessConfig()

        self.service = IngestionService(
            self.repository, self.blob_storage, self.vector_db, self.graph_db,
            self.chunking_config, self.staleness_config,
        )


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
