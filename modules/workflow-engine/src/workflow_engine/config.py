"""Configuration schema for the Workflow Engine module (LLD §4.5).

Loaded from a YAML file (path via WORKFLOW_ENGINE_CONFIG_FILE env var) with
environment-variable overrides on top, validated at startup via Pydantic.
Invalid configuration fails startup. Fields marked hot-reloadable in the LLD
are exposed through `HotReloadable` and can be changed at runtime via the
config API without a process restart; changes are published to Auditability.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RetryPolicyConfig(BaseModel):
    max_retries: int = 3
    backoff_strategy: Literal["exponential", "fixed", "none"] = "exponential"


class ExecutionConfig(BaseModel):
    default_confidence_threshold: float = Field(0.85, ge=0.0, le=1.0)  # hot-reloadable
    max_parallel_steps_per_instance: int = 10
    default_step_timeout_seconds: int = 30
    default_retry_policy: RetryPolicyConfig = RetryPolicyConfig()


class ReplanningConfig(BaseModel):
    enabled: bool = True  # hot-reloadable
    max_replan_attempts_per_instance: int = 2


class HumanOversightConfig(BaseModel):
    default_approval_timeout_seconds: int = 86400
    escalation_on_timeout: bool = True


class SimulationSandboxConfig(BaseModel):
    enabled: bool = True  # feature flag


class EventPublishingConfig(BaseModel):
    destinations: list[str] = Field(
        default_factory=lambda: ["observability", "auditability", "evaluation_framework"]
    )
    async_delivery: bool = True
    retry_on_publish_failure: bool = True


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"  # hot-reloadable
    debug_content_logging: bool = False  # feature flag, per-tenant, default false


class WorkflowEngineSettings(BaseSettings):
    """Root settings object, mirrors the `workflow_engine:` YAML document."""

    model_config = SettingsConfigDict(
        env_prefix="WORKFLOW_ENGINE_",
        env_nested_delimiter="__",
        extra="forbid",
    )

    tenant_id: str = "default"
    execution: ExecutionConfig = ExecutionConfig()
    replanning: ReplanningConfig = ReplanningConfig()
    human_oversight: HumanOversightConfig = HumanOversightConfig()
    simulation_sandbox: SimulationSandboxConfig = SimulationSandboxConfig()
    event_publishing: EventPublishingConfig = EventPublishingConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    # Infra connection settings — not part of the tenant-facing YAML schema,
    # supplied via environment in every deployment target (Helm, compose, CI).
    database_url: str = "postgresql+asyncpg://workflow_engine:workflow_engine@localhost:5432/workflow_engine"
    kafka_bootstrap_servers: str = "localhost:9092"
    service_name: str = "workflow-engine"
    http_port: int = 8080
    # Base URL for LLM Gateway / Tool Orchestration / Guardrails / Human
    # Oversight when none of those modules is deployed yet — points at the
    # dependency-stub service from deploy/docker-compose.yml (LLD's
    # Deployability and Testability Contract). Override per-dependency once
    # each real module exists.
    dependency_stub_base_url: str = "http://localhost:9100"

    # Hot-reloadable field names, for the config API to validate against.
    HOT_RELOADABLE_PATHS: tuple[str, ...] = (
        "execution.default_confidence_threshold",
        "replanning.enabled",
        "telemetry.log_level",
    )


_HOT_RELOADABLE = {
    "execution.default_confidence_threshold",
    "replanning.enabled",
    "telemetry.log_level",
}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> WorkflowEngineSettings:
    """Load settings from an optional YAML file, then apply env overrides.

    Pydantic Settings applies env vars on top of whatever we pass in as the
    initial "YAML-sourced" values, matching the base -> env override order
    described in the LLD's configurability principle (§4.9), one level up
    from the tenant/definition/step tiers those fields belong to.
    """
    yaml_path = os.environ.get("WORKFLOW_ENGINE_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("workflow_engine", raw)
    return WorkflowEngineSettings(**overrides)
