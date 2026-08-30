"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from guardrails.config import GuardrailsSettings
from guardrails.core.ports import LLMGatewayClient, SentinelAgentsClient


@dataclass
class AppContext:
    settings: GuardrailsSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    llm_gateway: LLMGatewayClient
    sentinel_agents: SentinelAgentsClient
