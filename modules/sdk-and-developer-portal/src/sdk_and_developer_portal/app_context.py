"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sdk_and_developer_portal.config import SdkAndDeveloperPortalSettings
from sdk_and_developer_portal.core.ports import (
    AuditabilityClient,
    IdentityAccessClient,
    ModuleSpecClient,
    MultiTenancyClient,
)


@dataclass
class AppContext:
    settings: SdkAndDeveloperPortalSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    identity_access: IdentityAccessClient
    multi_tenancy: MultiTenancyClient
    auditability: AuditabilityClient
    module_spec: ModuleSpecClient
