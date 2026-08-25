"""Configuration schema for the PromptOps module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class PromptOpsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PROMPTOPS_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://promptops:promptops@localhost:5432/promptops"

    # Pool sized against this module's own Helm chart (deploy/helm/promptops/values.yaml):
    # maxReplicas=10 (operator/CI-driven prompt governance, not per-request serving
    # volume -- the same lighter ceiling LLMOps' own chart already uses), targeting
    # <=100 steady-state / <=150 burst connections platform-wide at full autoscale,
    # this platform's standard sizing formula.
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "promptops"
    http_port: int = 8108

    # A/B Testing Service thresholds (core/ab_testing_service.py):
    min_ab_sample_size_per_arm: int = 10
    ab_significance_level: float = 0.05

    # Drift Detection Service (core/drift_detection_service.py): reuses the same z-test.
    drift_significance_level: float = 0.05

    # Reflection Optimiser (core/reflection_optimiser.py): the one bounded autonomous
    # action this module takes -- proposing a new draft, never auto-deploying it.
    max_pass_rate_before_reflection: float = 0.9
    min_reflection_sample_size: int = 10
    reflection_model: str = "gpt-4o-mini"

    evaluation_framework_base_url: str = "http://localhost:8097"
    llm_gateway_base_url: str = "http://localhost:8082"
    dependency_stub_base_url: str = "http://localhost:9129"

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


def load_settings() -> PromptOpsSettings:
    yaml_path = os.environ.get("PROMPTOPS_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("promptops", raw)
    return PromptOpsSettings(**overrides)
