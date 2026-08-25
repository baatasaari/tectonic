"""Configuration schema for the Secrets and Credential Management module
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


class SecretsAndCredentialManagementSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SECRETS_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = (
        "postgresql+asyncpg://secrets_and_credential_management:secrets_and_credential_management"
        "@localhost:5432/secrets_and_credential_management"
    )

    # Pool sized against this module's own Helm chart
    # (deploy/helm/secrets-and-credential-management/values.yaml): maxReplicas=10 --
    # a security-critical, latency-sensitive but not front-door-volume path, this
    # platform's standard sizing formula.
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "secrets-and-credential-management"
    http_port: int = 8111

    identity_access_base_url: str = "http://localhost:8110"
    auditability_base_url: str = "http://localhost:8090"
    dependency_stub_base_url: str = "http://localhost:9132"

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

    # security/envelope_encryption.py's own key -- encrypts every secret value at rest.
    # A real, valid Fernet key (32 random bytes, url-safe base64), but an obviously
    # insecure, publicly-known default so local dev/tests work with zero config; main.py
    # logs a startup warning if it's still active. NEVER the same secret as
    # jwt_shared_secret -- a completely different trust boundary.
    secrets_master_key: str = Field(
        default="TjDlTNIHnInVxA0zsGHYi6iTjBRtCSnWVcGxrYLXaYc=", validation_alias="SECRETS_MASTER_KEY",
    )


def load_settings() -> SecretsAndCredentialManagementSettings:
    yaml_path = os.environ.get("SECRETS_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("secrets-and-credential-management", raw)
    return SecretsAndCredentialManagementSettings(**overrides)
