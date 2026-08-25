"""Configuration schema for the Identity and Access module (LLD §Level 4
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


class IdentityAndAccessSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IDENTITY_ACCESS_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://identity_access:identity_access@localhost:5432/identity_access"

    # Pool sized against this module's own Helm chart (deploy/helm/identity-and-access/values.yaml):
    # maxReplicas=20 -- `authorize` is meant to sit on other modules' hot request paths
    # (see the LLD's own non-functional targets), closer to the platform's high-QPS
    # front-door modules than the operator-facing registries.
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "identity-access"
    http_port: int = 8110

    token_default_ttl_seconds: int = 3600

    auditability_base_url: str = "http://localhost:8090"
    dependency_stub_base_url: str = "http://localhost:9131"

    # Service-to-service JWT auth (security/jwt_auth.py) — one shared secret across
    # every module, so this field's env var name is NOT prefixed like the rest of this
    # settings class: every module's Helm chart injects the same Kubernetes Secret under
    # this same literal env var name. Protects this module's OWN inbound API -- the
    # coarse, platform-wide, module-to-module trust boundary. The default is an
    # insecure, obviously-a-placeholder value so local dev/tests work with zero config;
    # main.py logs a startup warning if it's still active.
    jwt_shared_secret: str = Field(
        default="dev-insecure-shared-secret-change-me", validation_alias="TECTONIC_JWT_SHARED_SECRET",
    )
    jwt_ttl_seconds: int = 300

    # security/token_signer.py's own signing key -- deliberately DISTINCT from
    # jwt_shared_secret above. Signs the fine-grained, per-identity, zero-trust scoped
    # tokens this module itself issues (core/token_service.py); compromising the coarse
    # platform-wide service secret must never compromise these.
    token_signing_secret: str = "dev-insecure-token-signing-secret-change-me"


def load_settings() -> IdentityAndAccessSettings:
    yaml_path = os.environ.get("IDENTITY_ACCESS_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("identity-access", raw)
    return IdentityAndAccessSettings(**overrides)
