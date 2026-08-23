"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from long_term_memory.config import LongTermMemorySettings
from long_term_memory.core.ports import (
    GraphDBClient,
    GuardrailsClient,
    LLMGatewayClient,
    VectorDBClient,
)


@dataclass
class AppContext:
    settings: LongTermMemorySettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    vector_db: VectorDBClient
    graph_db: GraphDBClient
    llm_gateway: LLMGatewayClient
    guardrails: GuardrailsClient
