"""Configuration schema for the LLM Gateway module (LLD §Level 4 "Configuration")."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RoutingConfig(BaseModel):
    strategy: Literal["quality_weighted", "cost_optimised", "latency_optimised"] = "quality_weighted"
    quality_weight: float = 0.5  # hot-reloadable, should sum sensibly with cost/latency weights
    cost_weight: float = 0.3
    latency_weight: float = 0.2


class CacheConfig(BaseModel):
    semantic_cache_enabled: bool = True
    similarity_threshold: float = Field(0.92, ge=0.0, le=1.0)  # hot-reloadable
    staleness_detection_enabled: bool = True


class FailoverConfig(BaseModel):
    max_provider_attempts: int = 3
    provider_priority_override: list[str] = Field(default_factory=list)


class BudgetConfig(BaseModel):
    enforce_hard_limit: bool = True  # if false, alert only, do not block


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"
    debug_content_logging: bool = False


class LLMGatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_GATEWAY_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    routing: RoutingConfig = RoutingConfig()
    cache: CacheConfig = CacheConfig()
    failover: FailoverConfig = FailoverConfig()
    budget: BudgetConfig = BudgetConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://llm_gateway:llm_gateway@localhost:5432/llm_gateway"

    # Pool sized against this module's own Helm chart (deploy/helm/llm-gateway/values.yaml):
    # maxReplicas=30, targeting <=100 steady-state / <=150 burst connections to
    # this module's own Postgres instance platform-wide at full autoscale.
    db_pool_size: int = 4
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    redis_url: str = "redis://localhost:6379/0"
    service_name: str = "llm-gateway"
    multi_tenancy_base_url: str = "http://localhost:8109"
    entitlement_gate_cache_ttl_seconds: float = 30.0
    http_port: int = 8082
    secrets_and_credential_management_base_url: str = "http://localhost:8111"

    # Service-to-service JWT auth (security/jwt_auth.py) — one shared secret across
    # every module, so this field's env var name is NOT prefixed like the rest of this
    # settings class: every module's Helm chart injects the same Kubernetes Secret under
    # this same literal env var name. The default is an insecure, obviously-a-placeholder
    # value so local dev/tests work with zero config; main.py logs a startup warning if
    # it's still active.
    jwt_shared_secret: str = Field(
        default="dev-insecure-shared-secret-change-me", validation_alias="TECTONIC_JWT_SHARED_SECRET",
    )
    jwt_ttl_seconds: int = 300


_HOT_RELOADABLE = {
    "routing.quality_weight",
    "cache.similarity_threshold",
    "telemetry.log_level",
}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> LLMGatewaySettings:
    yaml_path = os.environ.get("LLM_GATEWAY_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("llm_gateway", raw)
    return LLMGatewaySettings(**overrides)
