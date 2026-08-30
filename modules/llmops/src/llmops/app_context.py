"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from llmops.config import LLMOpsSettings
from llmops.core.ports import EvaluationFrameworkClient


@dataclass
class AppContext:
    settings: LLMOpsSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    evaluation_framework: EvaluationFrameworkClient
