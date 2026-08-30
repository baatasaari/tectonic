"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from mcp_gateway.config import MCPGatewaySettings
from mcp_gateway.core.ports import MCPBackendClient


@dataclass
class AppContext:
    settings: MCPGatewaySettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    backend: MCPBackendClient
