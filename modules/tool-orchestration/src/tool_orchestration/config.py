"""Configuration schema for the Tool Orchestration module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CircuitBreakerConfig(BaseModel):
    failure_threshold: float = Field(0.5, ge=0.0, le=1.0)  # hot-reloadable
    open_duration_seconds: int = 60


class RetryConfig(BaseModel):
    default_max_retries: int = 3
    default_backoff_strategy: Literal["exponential", "fixed", "none"] = "exponential"


class SynthesisConfig(BaseModel):
    enabled: bool = False  # feature flag, default off, opt-in per tenant
    require_sentinel_approval: bool = True  # cannot be disabled if synthesis is enabled


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"
    debug_content_logging: bool = False


class ToolOrchestrationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TOOL_ORCHESTRATION_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    circuit_breaker: CircuitBreakerConfig = CircuitBreakerConfig()
    retry: RetryConfig = RetryConfig()
    synthesis: SynthesisConfig = SynthesisConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://tool_orchestration:tool_orchestration@localhost:5432/tool_orchestration"

    # Pool sized against this module's own Helm chart (deploy/helm/tool-orchestration/values.yaml):
    # maxReplicas=20, targeting <=100 steady-state / <=150 burst connections to
    # this module's own Postgres instance platform-wide at full autoscale.
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    redis_url: str = "redis://localhost:6379/0"
    service_name: str = "tool-orchestration"
    multi_tenancy_base_url: str = "http://localhost:8109"
    entitlement_gate_cache_ttl_seconds: float = 30.0
    http_port: int = 8083
    llm_gateway_base_url: str = "http://localhost:8082"
    guardrails_base_url: str = "http://localhost:8093"
    sentinel_agents_base_url: str = "http://localhost:8094"

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

    def model_post_init(self, context: Any, /) -> None:
        if self.synthesis.enabled and not self.synthesis.require_sentinel_approval:
            raise ValueError("synthesis.require_sentinel_approval cannot be disabled while synthesis is enabled")


_HOT_RELOADABLE = {
    "circuit_breaker.failure_threshold",
    "telemetry.log_level",
}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> ToolOrchestrationSettings:
    yaml_path = os.environ.get("TOOL_ORCHESTRATION_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("tool_orchestration", raw)
    return ToolOrchestrationSettings(**overrides)
