"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from finops.config import FinOpsSettings
from finops.core.ports import LLMGatewaySpendClient


@dataclass
class AppContext:
    settings: FinOpsSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    llm_gateway: LLMGatewaySpendClient
