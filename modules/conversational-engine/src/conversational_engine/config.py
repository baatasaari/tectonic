"""Configuration schema for the Conversational Engine module (LLD §Level 4
"Configuration"). Loaded from YAML (WORKFLOW_ENGINE-style env override), same
base -> tenant -> definition -> step resolution principle Module 1 sets as
the platform-wide convention.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SessionConfig(BaseModel):
    ttl_seconds: int = 1800  # hot-reloadable, Redis session expiry
    cross_channel_continuity: bool = True  # feature flag, requires Long-Term Memory


class PersonaConfig(BaseModel):
    default_persona_config_ref: str = "default"


class HandoffConfig(BaseModel):
    emotion_score_threshold: float = Field(0.75, ge=0.0, le=1.0)  # hot-reloadable
    repeated_refusal_threshold: int = 3


class StreamingConfig(BaseModel):
    protocol: Literal["sse", "websocket"] = "sse"


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"
    debug_content_logging: bool = False


class ConversationalEngineSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CONVERSATIONAL_ENGINE_", env_nested_delimiter="__", extra="forbid"
    )

    tenant_id: str = "default"
    session: SessionConfig = SessionConfig()
    persona: PersonaConfig = PersonaConfig()
    handoff: HandoffConfig = HandoffConfig()
    streaming: StreamingConfig = StreamingConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://conversational_engine:conversational_engine@localhost:5432/conversational_engine"
    redis_url: str = "redis://localhost:6379/0"
    service_name: str = "conversational-engine"
    http_port: int = 8081
    # Points at the dependency-stub service for LLM Gateway / Guardrails /
    # Long-Term Memory / Human Oversight until those modules are deployed for
    # real (LLM Gateway now exists as Module 3 — point this at its real base
    # URL in any environment where both are deployed).
    dependency_stub_base_url: str = "http://localhost:9101"

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


_HOT_RELOADABLE = {
    "session.ttl_seconds",
    "handoff.emotion_score_threshold",
    "telemetry.log_level",
}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> ConversationalEngineSettings:
    yaml_path = os.environ.get("CONVERSATIONAL_ENGINE_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("conversational_engine", raw)
    return ConversationalEngineSettings(**overrides)
