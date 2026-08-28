"""Configuration schema for the Multi-tenancy module (LLD §Level 4
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


class ProbeTargetConfig(BaseModel):
    """One module the Isolation Probe Service can check. Every module in
    this platform already exposes `GET {base_url}{list_path}?tenant_id=X`
    returning `{"items": [...each with its own tenant_id...]}` -- the
    identical contract this module's `TenantScopedListClient` relies on,
    so adding a new target needs only a config entry, never new code.
    `audience` is the target module's own `service_name`, used to scope
    this probe's outbound JWT to it."""

    name: str
    base_url: str
    list_path: str
    audience: str


class MultiTenancySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MULTI_TENANCY_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://multi_tenancy:multi_tenancy@localhost:5432/multi_tenancy"

    # Pool sized against this module's own Helm chart (deploy/helm/multi-tenancy/values.yaml):
    # maxReplicas=10 (operator/CI-driven registry and probe traffic, not per-request
    # serving volume, EXCEPT for the gate-check endpoint which other modules' hot paths
    # are meant to call -- see the LLD's own non-functional targets), this platform's
    # standard sizing formula.
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "multi-tenancy"
    http_port: int = 8109

    # Isolation Probe Service targets (core/isolation_probe_service.py). Defaults to Agent
    # Cards (Module 23) -- a real, already-built peer following this platform's shared
    # tenant-scoped list contract.
    probe_targets: list[ProbeTargetConfig] = [
        ProbeTargetConfig(name="agent-cards", base_url="http://localhost:8102", list_path="/v1/agent-cards", audience="agent-cards"),
    ]

    auditability_base_url: str = "http://localhost:8099"

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


def load_settings() -> MultiTenancySettings:
    yaml_path = os.environ.get("MULTI_TENANCY_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("multi-tenancy", raw)
    return MultiTenancySettings(**overrides)
