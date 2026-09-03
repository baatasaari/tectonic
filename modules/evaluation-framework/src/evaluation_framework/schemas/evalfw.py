"""Request/response models for `/v1/evaluation-framework/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


def _reject_null_byte(value: str) -> str:
    """Postgres's `text`/`varchar` columns are UTF-8 and reject the NUL
    byte outright (`asyncpg.exceptions.CharacterNotInRepertoireError`) --
    a value `str` is happy to hold but the database is not. Schema-valid
    per OpenAPI (`type: string` says nothing about NUL), so nothing
    upstream of the DB call rejects it without this: caught here as a
    clean `422` instead of the request reaching the database at all
    (found by this module's own new contract-test tier -- the same fix
    Multi-tenancy's, Billing and Metering's, and LLM Gateway's own
    `_reject_null_byte` already established; ticket #82's platform-wide
    sweep covered this module's *query* parameters, `tenant_id`/
    `agent_ref` in `routes_evalfw.py`'s `_reject_null_byte_query`, but
    never these *body* fields, which reach the exact same
    `session.execute()` calls unguarded). Applied to every string field
    that ends up persisted as a scalar Postgres column -- not
    `agent_output`/`reference_data`, which are never persisted here."""
    if "\x00" in value:
        raise ValueError("must not contain a NUL byte (unsupported by Postgres's text encoding)")
    return value


class MetricScoreSchema(BaseModel):
    id: str
    metric_name: str
    score: float
    threshold: float
    passed: bool
    created_at: datetime


class MetricScoreListResponse(BaseModel):
    items: list[MetricScoreSchema]
    total: int
    limit: int
    offset: int


class EvaluateRequest(BaseModel):
    tenant_id: str
    agent_ref: str
    agent_output: str
    reference_data: dict[str, Any] | None = None
    metric_set: list[str]
    trigger_source: str = "ci_cd"

    @field_validator("tenant_id", "agent_ref", "trigger_source")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)

    @field_validator("metric_set")
    @classmethod
    def _validate_metric_set(cls, value: list[str]) -> list[str]:
        for item in value:
            _reject_null_byte(item)
        return value


class EvalRunSchema(BaseModel):
    id: str
    tenant_id: str
    trigger_source: str
    agent_ref: str
    metrics_evaluated: list[str]
    status: str
    started_at: datetime
    completed_at: datetime | None
    scores: list[MetricScoreSchema] = []


class EvalRunListResponse(BaseModel):
    items: list[EvalRunSchema]
    total: int
    limit: int
    offset: int


class GateRequest(BaseModel):
    tenant_id: str
    eval_run_id: str
    environment: str = "production"

    @field_validator("tenant_id", "eval_run_id", "environment")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)


class GateResultSchema(BaseModel):
    id: str
    eval_run_id: str
    overall_passed: bool
    blocking_failures: list[str]
    environment: str
    created_at: datetime


class CreateDomainPackRequest(BaseModel):
    tenant_id: str
    pack_name: str
    custom_thresholds: dict[str, float] = {}

    @field_validator("tenant_id", "pack_name")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)

    @field_validator("custom_thresholds")
    @classmethod
    def _validate_custom_thresholds_keys(cls, value: dict[str, float]) -> dict[str, float]:
        """A NUL byte survives inside a dict *key* too -- `custom_thresholds`
        round-trips as a real Postgres `jsonb` column (`DomainMetricPack.
        custom_thresholds`), and jsonb's own text-based storage rejects an
        embedded NUL exactly the way `text`/`varchar` does, whether it's a
        top-level string field or nested inside a JSON object's key (found
        by this module's own contract-test tier; the same fix Billing and
        Metering's own `unit_prices` key validator already established)."""
        for key in value:
            _reject_null_byte(key)
        return value


class DomainMetricPackSchema(BaseModel):
    id: str
    tenant_id: str
    pack_name: str
    enabled: bool
    custom_thresholds: dict[str, float]


class SampleRequest(BaseModel):
    tenant_id: str
    interaction_id: str
    agent_ref: str
    agent_output: str
    reference_data: dict[str, Any] | None = None
    metric_set: list[str]

    # `interaction_id` is deliberately not validated here -- it's only ever hashed
    # (`ProductionSampler.should_sample`), never persisted to Postgres, so it's out
    # of this bug class's scope (the same "reaches asyncpg/Postgres unguarded"
    # scoping Vector DB's own README documents for its analogous case).
    @field_validator("tenant_id", "agent_ref")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)

    @field_validator("metric_set")
    @classmethod
    def _validate_metric_set(cls, value: list[str]) -> list[str]:
        for item in value:
            _reject_null_byte(item)
        return value


class SampleResponse(BaseModel):
    sampled: bool
    eval_run_id: str | None = None
