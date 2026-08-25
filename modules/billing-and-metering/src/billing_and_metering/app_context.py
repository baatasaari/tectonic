"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from billing_and_metering.config import BillingAndMeteringSettings
from billing_and_metering.core.ports import AuditabilityClient, FinOpsClient


@dataclass
class AppContext:
    settings: BillingAndMeteringSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    finops: FinOpsClient
    auditability: AuditabilityClient
