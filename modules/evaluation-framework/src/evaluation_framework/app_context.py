"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from evaluation_framework.config import EvaluationFrameworkSettings
from evaluation_framework.core.ports import LLMGatewayClient
from evaluation_framework.core.sampler import ProductionSampler


@dataclass
class AppContext:
    settings: EvaluationFrameworkSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    llm_gateway: LLMGatewayClient
    sampler: ProductionSampler
