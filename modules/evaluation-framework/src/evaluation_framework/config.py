"""Configuration schema for the Evaluation Framework module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MetricsConfig(BaseModel):
    enabled_libraries: list[str] = ["faithfulness", "coherence", "tool_trace_correctness"]
    domain_packs: list[str] = []  # e.g. ["financial_guidance_compliance"]


class GatingConfig(BaseModel):
    thresholds: dict[str, float] = {"faithfulness": 0.85, "tool_trace_correctness": 0.9, "coherence": 0.6}  # hot-reloadable


class ProductionSamplingConfig(BaseModel):
    enabled: bool = True
    sample_rate: float = 0.05  # hot-reloadable


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class EvaluationFrameworkSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EVALUATION_FRAMEWORK_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    metrics: MetricsConfig = MetricsConfig()
    gating: GatingConfig = GatingConfig()
    production_sampling: ProductionSamplingConfig = ProductionSamplingConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://evalfw:evalfw@localhost:5432/evalfw"

    # Pool sized against this module's own Helm chart (deploy/helm/evaluation-framework/values.yaml):
    # maxReplicas=20, targeting <=100 steady-state / <=150 burst connections to
    # this module's own Postgres instance platform-wide at full autoscale.
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "evaluation-framework"
    multi_tenancy_base_url: str = "http://localhost:8109"
    entitlement_gate_cache_ttl_seconds: float = 30.0
    http_port: int = 8097
    llm_gateway_base_url: str = "http://localhost:8082"

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


_HOT_RELOADABLE = {"gating.thresholds", "production_sampling.sample_rate"}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> EvaluationFrameworkSettings:
    yaml_path = os.environ.get("EVALUATION_FRAMEWORK_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("evaluation_framework", raw)
    return EvaluationFrameworkSettings(**overrides)
