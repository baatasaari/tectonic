"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from knowledge_base.config import KnowledgeBaseSettings
from knowledge_base.core.ports import BlobStorage, GraphDBClient, VectorDBClient


@dataclass
class AppContext:
    settings: KnowledgeBaseSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    blob_storage: BlobStorage
    vector_db: VectorDBClient
    graph_db: GraphDBClient
