"""Configuration schema for the Auditability module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class NLQueryConfig(BaseModel):
    enabled: bool = True  # feature flag; disabled -> 400 with a clear message, not a silent no-op


class AuditPackConfig(BaseModel):
    worker_poll_interval_seconds: float = 5.0
    worker_lease_seconds: int = 120
    worker_max_attempts: int = 3
    output_format: str = "pdf"


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class AuditabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUDITABILITY_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    nl_query: NLQueryConfig = NLQueryConfig()
    audit_pack: AuditPackConfig = AuditPackConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://auditability:auditability@localhost:5432/auditability"

    # Pool sized against this module's own Helm chart (deploy/helm/auditability/values.yaml):
    # maxReplicas=20 (this module sits on the platform's write-heavy hot path -- every other
    # module's event emission lands here), targeting <=100 steady-state / <=150 burst
    # connections to this module's own Postgres instance platform-wide at full autoscale.
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "auditability"
    http_port: int = 8099
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


def load_settings() -> AuditabilitySettings:
    yaml_path = os.environ.get("AUDITABILITY_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("auditability", raw)
    return AuditabilitySettings(**overrides)
