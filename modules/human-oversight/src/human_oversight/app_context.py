"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from human_oversight.config import HumanOversightSettings
from human_oversight.core.ports import (
    AuditabilityClient,
    DecisionCallbackDispatcher,
    NotificationChannel,
)


@dataclass
class AppContext:
    settings: HumanOversightSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    notification_channels: dict[str, NotificationChannel]
    callback_dispatcher: DecisionCallbackDispatcher
    auditability: AuditabilityClient
