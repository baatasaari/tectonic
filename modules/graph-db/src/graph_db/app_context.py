"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from graph_db.config import GraphDbSettings
from graph_db.core.ports import AuditabilityClient


@dataclass
class AppContext:
    settings: GraphDbSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    auditability: AuditabilityClient
