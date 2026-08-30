"""Request/response models for `/v1/vector-db/*` (LLD §3)."""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

# Qdrant stores dense vectors as float32 internally (~3.4e38 max magnitude); a
# schema-valid `float` (Python/JSON has no such ceiling) well beyond that overflows
# to +/-inf on Qdrant's own internal `np.array(vector, dtype=np.float32)` cast, and
# that non-finite value then corrupts its cosine-normalization
# (`vector_np / norm`, itself NaN once `norm` is inf) -- not a real embedding
# coordinate any provider would ever produce. Generous headroom under the real
# float32 ceiling, not a tight fit to it.
_MAX_VECTOR_COMPONENT_MAGNITUDE = 1e30


def _reject_empty_vector(value: list[float] | None) -> list[float] | None:
    """`vector` is schema-valid as an empty list (`type: array` says
    nothing about a minimum length), but a zero-dimensional embedding
    is nonsensical -- `Qdrant.create_collection` accepts `size=0`
    without complaint, then a later real read against that
    zero-dimension collection crashes deep inside the embedded local
    Qdrant client's own payload-mask calculation with an unhandled
    `IndexError` (found by this module's own OpenAPI contract-test
    tier). Caught here as a clean `422` instead."""
    if value is None:
        return None
    if len(value) == 0:
        raise ValueError("vector must not be empty when given (omit the field to let content be embedded instead)")
    for component in value:
        if not math.isfinite(component) or abs(component) > _MAX_VECTOR_COMPONENT_MAGNITUDE:
            raise ValueError(
                f"vector components must be finite and no larger in magnitude than "
                f"{_MAX_VECTOR_COMPONENT_MAGNITUDE:g} -- not a real embedding coordinate"
            )
    return value


class IndexPointRequest(BaseModel):
    tenant_id: str
    source_module: str
    source_ref: str
    content: str | None = None
    vector: list[float] | None = None
    payload: dict[str, Any] = {}
    embedding_model_version: str | None = None

    @field_validator("vector")
    @classmethod
    def _validate_vector(cls, value: list[float] | None) -> list[float] | None:
        return _reject_empty_vector(value)


class IndexPointResponse(BaseModel):
    id: str


class DeleteResponse(BaseModel):
    status: str


class QueryRequest(BaseModel):
    tenant_id: str
    text: str | None = None
    vector: list[float] | None = None
    filters: dict[str, Any] = {}
    # A non-positive limit is schema-valid for a bare `int` but crashes Qdrant's own
    # local query implementation with an unhandled `ValueError` instead of a clean
    # `422` (found by this module's own OpenAPI contract-test tier) -- `ge=1` lets
    # FastAPI/Pydantic reject it before it ever reaches the client.
    top_k: int | None = Field(default=None, ge=1)
    hybrid: bool | None = None

    @field_validator("vector")
    @classmethod
    def _validate_vector(cls, value: list[float] | None) -> list[float] | None:
        return _reject_empty_vector(value)

    @field_validator("filters")
    @classmethod
    def _validate_filter_values(cls, value: dict[str, Any]) -> dict[str, Any]:
        # Each filter key becomes a Qdrant JSON-path payload field reference, and
        # each value a Qdrant `MatchValue` (qdrant_ops.build_filter) -- `filters:
        # dict[str, Any]` is schema-valid for an empty-string key or any JSON value
        # (null, a nested object, a list, ...) as the value, but an empty key isn't a
        # real payload field reference (Qdrant's own JSON-path parser raises a bare
        # `ValueError("Invalid path")`) and MatchValue only accepts bool/int/str
        # (a mismatched value raises an unhandled pydantic ValidationError deep in
        # the qdrant-client) -- neither reaches this module's own clean `422` path
        # without this (found by this module's own OpenAPI contract-test tier).
        for key, item in value.items():
            if not key:
                raise ValueError("filters keys must not be empty")
            if not isinstance(item, bool | int | str):
                # ValueError, not TypeError: FastAPI's request-body validation only
                # turns a ValueError raised inside a field_validator into a clean 422 --
                # a TypeError instead propagates as an unhandled 500 (verified directly;
                # ruff's TRY004 suggestion to prefer TypeError here is wrong for this
                # FastAPI/pydantic context).
                raise ValueError(  # noqa: TRY004
                    f"filters[{key!r}] must be a bool, int, or str to match against, got {item!r}"
                )
        return value


class ScoredResultSchema(BaseModel):
    id: str
    score: float
    payload: dict[str, Any]


class QueryResponse(BaseModel):
    results: list[ScoredResultSchema]


def _reject_null_byte(value: str) -> str:
    """Postgres's `text`/`varchar` columns are UTF-8 and reject the NUL
    byte outright (`asyncpg.exceptions.CharacterNotInRepertoireError`)
    -- a value `str` is happy to hold but the database is not.
    Schema-valid per OpenAPI (`type: string` says nothing about NUL),
    so nothing upstream of the DB call rejects it without this: caught
    here as a clean `422` instead of the request reaching the database
    at all (found by this module's own OpenAPI contract-test tier --
    the same fix Billing and Metering's/Multi-tenancy's own
    `_reject_null_byte` already established)."""
    if "\x00" in value:
        raise ValueError("must not contain a NUL byte (unsupported by Postgres's text encoding)")
    return value


class StartMigrationRequest(BaseModel):
    tenant_id: str
    new_embedding_model: str

    @field_validator("tenant_id", "new_embedding_model")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)


class MigrationResponse(BaseModel):
    migration_id: str
    status: str


class MigrationStatusResponse(BaseModel):
    migration_id: str
    status: str
    progress: float
    points_total: int
    points_migrated: int
    created_at: datetime
    completed_at: datetime | None
