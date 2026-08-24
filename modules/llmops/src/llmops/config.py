"""Configuration schema for the LLMOps module (LLD §Level 4 "Configuration")."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class LLMOpsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLMOPS_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://llmops:llmops@localhost:5432/llmops"

    # Pool sized against this module's own Helm chart (deploy/helm/llmops/values.yaml):
    # maxReplicas=10 (operator/CI-driven traffic, not per-request serving volume -- a
    # lighter ceiling than the high-QPS registries like MCP/Agent Cards), targeting
    # <=100 steady-state / <=150 burst connections platform-wide at full autoscale,
    # this platform's standard sizing formula.
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "llmops"
    http_port: int = 8104

    # The canary gate (core/canary_evaluation_service.py): a promotion needs at least
    # this many real evaluation samples before it will even render a verdict, and the
    # real pass rate among them must meet this threshold.
    min_canary_sample_size: int = 10
    min_canary_pass_rate: float = 0.95

    evaluation_framework_base_url: str = "http://localhost:8097"
    dependency_stub_base_url: str = "http://localhost:9125"

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


def load_settings() -> LLMOpsSettings:
    yaml_path = os.environ.get("LLMOPS_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("llmops", raw)
    return LLMOpsSettings(**overrides)
