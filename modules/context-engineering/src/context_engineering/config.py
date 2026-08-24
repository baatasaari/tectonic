"""Configuration schema for the Context Engineering module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OntologyConfig(BaseModel):
    active_version: str = ""


class PrioritisationConfig(BaseModel):
    learning_enabled: bool = True  # consume Evaluation Framework feedback
    default_task_type_weights: dict[str, float] = Field(default_factory=dict)


class BudgetConfig(BaseModel):
    default_token_budget: int = Field(4000, gt=0)  # hot-reloadable, overridable per call
    summarisation_enabled: bool = True


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class ContextEngineeringSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONTEXT_ENGINEERING_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    ontology: OntologyConfig = OntologyConfig()
    prioritisation: PrioritisationConfig = PrioritisationConfig()
    budget: BudgetConfig = BudgetConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://context_engineering:context_engineering@localhost:5432/context_engineering"
    service_name: str = "context-engineering"
    http_port: int = 8086
    dependency_stub_base_url: str = "http://localhost:9107"

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


_HOT_RELOADABLE = {"budget.default_token_budget"}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> ContextEngineeringSettings:
    yaml_path = os.environ.get("CONTEXT_ENGINEERING_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("context_engineering", raw)
    return ContextEngineeringSettings(**overrides)
