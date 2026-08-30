"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from promptops.config import PromptOpsSettings
from promptops.core.ports import EvaluationFrameworkClient, LLMGatewayClient


@dataclass
class AppContext:
    settings: PromptOpsSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    evaluation_framework: EvaluationFrameworkClient
    llm_gateway: LLMGatewayClient
