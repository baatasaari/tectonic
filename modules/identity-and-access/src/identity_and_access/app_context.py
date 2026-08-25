"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from identity_and_access.config import IdentityAndAccessSettings
from identity_and_access.core.ports import AuditabilityClient
from identity_and_access.security.token_signer import JWTTokenSigner


@dataclass
class AppContext:
    settings: IdentityAndAccessSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    auditability: AuditabilityClient
    signer: JWTTokenSigner
