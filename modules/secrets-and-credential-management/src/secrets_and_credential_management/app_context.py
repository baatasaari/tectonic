"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from secrets_and_credential_management.config import SecretsAndCredentialManagementSettings
from secrets_and_credential_management.core.ports import AuditabilityClient, IdentityAccessClient
from secrets_and_credential_management.security.envelope_encryption import EnvelopeCipher


@dataclass
class AppContext:
    settings: SecretsAndCredentialManagementSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    identity_access: IdentityAccessClient
    auditability: AuditabilityClient
    cipher: EnvelopeCipher
