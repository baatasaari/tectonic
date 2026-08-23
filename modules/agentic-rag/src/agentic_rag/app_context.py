"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from agentic_rag.config import AgenticRAGSettings
from agentic_rag.core.ports import (
    GraphDBClient,
    KnowledgeBaseClient,
    LLMGatewayClient,
    VectorDBClient,
)


@dataclass
class AppContext:
    settings: AgenticRAGSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    vector_db: VectorDBClient
    graph_db: GraphDBClient
    knowledge_base: KnowledgeBaseClient
    llm_gateway: LLMGatewayClient
