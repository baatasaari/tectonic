"""Configuration schema for the Data Source Plugins module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DriftConfig(BaseModel):
    auto_adapt_enabled: bool = True  # hot-reloadable; if false, always requires manual review
    auto_adapt_scope: Literal["additive_only", "additive_and_type_widening"] = "additive_only"


class QualityConfig(BaseModel):
    completeness_weight: float = Field(0.4, ge=0.0, le=1.0)
    freshness_weight: float = Field(0.3, ge=0.0, le=1.0)
    format_validity_weight: float = Field(0.3, ge=0.0, le=1.0)
    quality_gate_threshold: float = Field(0.6, ge=0.0, le=1.0)  # syncs below this are flagged, not blocked by default


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class DataSourcePluginsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATA_SOURCE_PLUGINS_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    drift: DriftConfig = DriftConfig()
    quality: QualityConfig = QualityConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://data_source_plugins:data_source_plugins@localhost:5432/data_source_plugins"

    # Pool sized against this module's own Helm chart (deploy/helm/data-source-plugins/values.yaml):
    # maxReplicas=20, targeting <=100 steady-state / <=150 burst connections to
    # this module's own Postgres instance platform-wide at full autoscale.
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "data-source-plugins"
    multi_tenancy_base_url: str = "http://localhost:8109"
    entitlement_gate_cache_ttl_seconds: float = 30.0
    http_port: int = 8087
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


_HOT_RELOADABLE = {"drift.auto_adapt_enabled"}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> DataSourcePluginsSettings:
    yaml_path = os.environ.get("DATA_SOURCE_PLUGINS_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("data_source_plugins", raw)
    return DataSourcePluginsSettings(**overrides)
