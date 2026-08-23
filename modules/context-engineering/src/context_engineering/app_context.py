"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from context_engineering.config import ContextEngineeringSettings
from context_engineering.core.ports import EvaluationFeedbackClient, LLMGatewayClient
from context_engineering.core.tokenization import TokenCounter


@dataclass
class AppContext:
    settings: ContextEngineeringSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    llm_gateway: LLMGatewayClient
    evaluation_feedback: EvaluationFeedbackClient
    token_counter: TokenCounter
