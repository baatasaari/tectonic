"""Process-wide wiring, mirroring Modules 1 and 2's app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from llm_gateway.clients.http_provider_client import HTTPProviderClient
from llm_gateway.config import LLMGatewaySettings
from llm_gateway.core.ports import (
    MultiTenancyQuotaClient,
    QualityScoreProvider,
    SecretsClient,
    SemanticCache,
)


@dataclass
class AppContext:
    settings: LLMGatewaySettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    cache: SemanticCache
    quality_scores: QualityScoreProvider
    secrets: SecretsClient
    provider_client: HTTPProviderClient
    multi_tenancy: MultiTenancyQuotaClient
