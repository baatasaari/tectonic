"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from vector_db.config import VectorDbSettings
from vector_db.core.migration_manager import MigrationManager
from vector_db.core.ports import EmbeddingProvider, MigrationRepository, MultiTenancyQuotaClient
from vector_db.core.vector_service import VectorService


@dataclass
class AppContext:
    settings: VectorDbSettings
    qdrant: AsyncQdrantClient
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    embeddings: EmbeddingProvider
    migration_repository: MigrationRepository
    vector_service: VectorService
    migration_manager: MigrationManager
    multi_tenancy: MultiTenancyQuotaClient
