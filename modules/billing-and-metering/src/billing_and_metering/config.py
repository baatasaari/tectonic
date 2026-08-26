"""Configuration schema for the Billing and Metering module
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


class BillingAndMeteringSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BILLING_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = (
        "postgresql+asyncpg://billing_and_metering:billing_and_metering"
        "@localhost:5432/billing_and_metering"
    )

    # Pool sized against this module's own Helm chart
    # (deploy/helm/billing-and-metering/values.yaml): maxReplicas=6 -- an
    # operator/back-office path, not a hot request path any other module blocks on.
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "billing-and-metering"
    http_port: int = 8112

    finops_base_url: str = "http://localhost:8105"
    auditability_base_url: str = "http://localhost:8090"
    multi_tenancy_base_url: str = "http://localhost:8109"
    dependency_stub_base_url: str = "http://localhost:9133"

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


def load_settings() -> BillingAndMeteringSettings:
    yaml_path = os.environ.get("BILLING_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("billing-and-metering", raw)
    return BillingAndMeteringSettings(**overrides)
