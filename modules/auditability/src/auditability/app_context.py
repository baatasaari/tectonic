"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from auditability.config import AuditabilitySettings
from auditability.core.ports import LLMGatewayClient


@dataclass
class AppContext:
    settings: AuditabilitySettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    llm_gateway: LLMGatewayClient
