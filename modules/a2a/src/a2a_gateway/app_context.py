"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from a2a_gateway.config import A2AGatewaySettings
from a2a_gateway.core.ports import A2APeerClient, WorkflowEngineClient


@dataclass
class AppContext:
    settings: A2AGatewaySettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    peer_client: A2APeerClient
    workflow_client: WorkflowEngineClient
