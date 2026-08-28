"""Configuration schema for the Long-Term Memory module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConsolidationConfig(BaseModel):
    schedule: Literal["hourly", "daily", "weekly"] = "daily"
    decay_threshold: float = Field(0.2, ge=0.0, le=1.0)  # hot-reloadable


class ReflectionConfig(BaseModel):
    enabled: bool = True  # feature flag
    trigger_source: str = "evaluation_framework"


class CrossAgentSharingConfig(BaseModel):
    enabled: bool = False  # feature flag, default off, opt-in per tenant
    visibility_policy_ref: str = ""


class ErasureConfig(BaseModel):
    sla_hours: int = Field(72, gt=0)


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class LongTermMemorySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LONG_TERM_MEMORY_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    consolidation: ConsolidationConfig = ConsolidationConfig()
    reflection: ReflectionConfig = ReflectionConfig()
    cross_agent_sharing: CrossAgentSharingConfig = CrossAgentSharingConfig()
    erasure: ErasureConfig = ErasureConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://long_term_memory:long_term_memory@localhost:5432/long_term_memory"

    # Pool sized against this module's own Helm chart (deploy/helm/long-term-memory/values.yaml):
    # maxReplicas=20, targeting <=100 steady-state / <=150 burst connections to
    # this module's own Postgres instance platform-wide at full autoscale.
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "long-term-memory"
    multi_tenancy_base_url: str = "http://localhost:8109"
    entitlement_gate_cache_ttl_seconds: float = 30.0
    http_port: int = 8092
    vector_db_base_url: str = "http://localhost:8089"
    graph_db_base_url: str = "http://localhost:8090"
    llm_gateway_base_url: str = "http://localhost:8082"
    guardrails_base_url: str = "http://localhost:8093"

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


_HOT_RELOADABLE = {"consolidation.decay_threshold"}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> LongTermMemorySettings:
    yaml_path = os.environ.get("LONG_TERM_MEMORY_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("long_term_memory", raw)
    return LongTermMemorySettings(**overrides)
