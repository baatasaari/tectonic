"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from multi_modality.config import MultiModalitySettings
from multi_modality.core.ports import GuardrailsClient


@dataclass
class AppContext:
    settings: MultiModalitySettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    guardrails: GuardrailsClient
