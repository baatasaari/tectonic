"""Configuration schema for the Regulatory and Compliance module (LLD
§Level 4 "Configuration")."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FrameworksConfig(BaseModel):
    enabled: list[str] = ["eu_ai_act", "nist_ai_rmf", "gdpr"]  # per-tenant selection


class EvidenceConfig(BaseModel):
    output_format: Literal["pdf", "json"] = "pdf"
    auto_generation_schedule: str | None = None  # e.g. "monthly", null means on-demand only


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class RegulatoryComplianceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REGULATORY_COMPLIANCE_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    frameworks: FrameworksConfig = FrameworksConfig()
    evidence: EvidenceConfig = EvidenceConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://regcomp:regcomp@localhost:5432/regcomp"
    service_name: str = "regulatory-compliance"
    http_port: int = 8096
    dependency_stub_base_url: str = "http://localhost:9117"
    mapping_table_path: str = ""  # empty = use bundled default; see core/mapping_data.py

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


_HOT_RELOADABLE = {"frameworks.enabled"}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> RegulatoryComplianceSettings:
    yaml_path = os.environ.get("REGULATORY_COMPLIANCE_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("regulatory_compliance", raw)
    return RegulatoryComplianceSettings(**overrides)
