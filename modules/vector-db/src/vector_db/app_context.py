"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient

from vector_db.config import VectorDbSettings
from vector_db.core.migration_manager import MigrationManager
from vector_db.core.ports import EmbeddingProvider, MigrationRepository
from vector_db.core.vector_service import VectorService


@dataclass
class AppContext:
    settings: VectorDbSettings
    qdrant: AsyncQdrantClient
    embeddings: EmbeddingProvider
    migration_repository: MigrationRepository
    vector_service: VectorService
    migration_manager: MigrationManager
