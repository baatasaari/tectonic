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
    # Pool sized against this module's own Helm chart (deploy/helm/workflow-engine/values.yaml):
    # maxReplicas=10, targeting <=100 steady-state / <=150 burst connections to
    # this module's own Postgres instance platform-wide at full autoscale.
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    kafka_bootstrap_servers: str = "localhost:9092"
    # Event outbox relay worker (core/outbox_worker.py) -- same tuning knobs, and same
    # defaults' rationale, as Regulatory Compliance's evidence-pack worker.
    outbox_worker_poll_interval_seconds: float = 1.0
    outbox_worker_lease_seconds: int = 60
    outbox_worker_max_attempts: int = 5
    service_name: str = "workflow-engine"
    multi_tenancy_base_url: str = "http://localhost:8109"
    entitlement_gate_cache_ttl_seconds: float = 30.0
    http_port: int = 8080
    llm_gateway_base_url: str = "http://localhost:8082"
    # Deliberately deployment-wide, not per-tenant/per-step -- see
    # clients/http_clients.py's HTTPLLMGatewayClient docstring (ticket #82).
    llm_gateway_virtual_key: str = "workflow-engine-default"
    tool_orchestration_base_url: str = "http://localhost:8083"
    guardrails_base_url: str = "http://localhost:8093"
    human_oversight_base_url: str = "http://localhost:8095"
    # Added for the intent step (ticket #82) -- this module had no Intent
    # Detection client at all before the Phase 2 support-agent slice.
    intent_detection_base_url: str = "http://localhost:8084"
    # Added for the retrieve step (ticket #82) -- likewise no Agentic RAG client before.
    agentic_rag_base_url: str = "http://localhost:8085"

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
