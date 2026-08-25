"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from multi_tenancy.config import MultiTenancySettings
from multi_tenancy.core.ports import TenantScopedListClient


@dataclass
class AppContext:
    settings: MultiTenancySettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    probe_clients: dict[str, TenantScopedListClient] = field(default_factory=dict)
