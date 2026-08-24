"""Configuration schema for the Agentic RAG module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RetrievalConfig(BaseModel):
    max_hops: int = Field(3, ge=1)  # hot-reloadable
    groundedness_threshold: float = Field(0.85, ge=0.0, le=1.0)  # hot-reloadable
    hybrid_retrieval_enabled: bool = True  # vector + graph + symbolic fan-out


class CriticConfig(BaseModel):
    method: Literal["llm", "heuristic"] = "llm"


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class AgenticRAGSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTIC_RAG_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    retrieval: RetrievalConfig = RetrievalConfig()
    critic: CriticConfig = CriticConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://agentic_rag:agentic_rag@localhost:5432/agentic_rag"
    service_name: str = "agentic-rag"
    http_port: int = 8085
    dependency_stub_base_url: str = "http://localhost:9106"

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


_HOT_RELOADABLE = {"retrieval.max_hops", "retrieval.groundedness_threshold"}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> AgenticRAGSettings:
    yaml_path = os.environ.get("AGENTIC_RAG_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("agentic_rag", raw)
    return AgenticRAGSettings(**overrides)
