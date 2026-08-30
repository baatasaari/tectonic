"""Configuration schema for the SDK and Developer Portal module
(LLD §Level 4 "Configuration")."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class CatalogTargetConfig(BaseModel):
    """One peer module this portal's catalogue syncs a real, live
    OpenAPI spec from -- the same configurable-target-list shape
    Multi-tenancy (Module 30)'s own `probe_targets` already
    established."""

    name: str
    base_url: str


class SdkAndDeveloperPortalSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SDKPORTAL_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = (
        "postgresql+asyncpg://sdk_and_developer_portal:sdk_and_developer_portal"
        "@localhost:5432/sdk_and_developer_portal"
    )

    # Pool sized against this module's own Helm chart
    # (deploy/helm/sdk-and-developer-portal/values.yaml): maxReplicas=6 -- a
    # developer-facing but not front-door-volume path.
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "sdk-and-developer-portal"
    http_port: int = 8113

    identity_access_base_url: str = "http://localhost:8110"
    multi_tenancy_base_url: str = "http://localhost:8109"
    auditability_base_url: str = "http://localhost:8099"
    dependency_stub_base_url: str = "http://localhost:9134"

    catalog_targets: list[CatalogTargetConfig] = Field(
        default_factory=lambda: [CatalogTargetConfig(name="auditability", base_url="http://localhost:8090")],
    )

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


def load_settings() -> SdkAndDeveloperPortalSettings:
    yaml_path = os.environ.get("SDKPORTAL_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("sdk-and-developer-portal", raw)
    return SdkAndDeveloperPortalSettings(**overrides)
