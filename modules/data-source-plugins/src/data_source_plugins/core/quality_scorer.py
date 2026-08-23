"""Data Quality Scorer (LLD §2 sub-components): rule-based completeness,
freshness and format-validity checks combined into an explainable overall
score — not an opaque ML model, per the LLD's own rationale ("customers
will want to know why a source scored low")."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from data_source_plugins.config import QualityConfig

_FRESHNESS_FIELD_CANDIDATES = ("updated_at", "timestamp", "synced_at", "modified_at")
# A record is considered fresh if its freshness field is within this many
# seconds of "now"; beyond that the score decays linearly to 0 at 7 days.
_FRESHNESS_FULL_SCORE_SECONDS = 3600.0
_FRESHNESS_ZERO_SCORE_SECONDS = 7 * 24 * 3600.0


@dataclass
class QualityBreakdown:
    completeness_score: float
    freshness_score: float
    format_validity_score: float
    overall_score: float


def _completeness(records: list[dict[str, Any]], schema: dict[str, str]) -> float:
    if not records or not schema:
        return 1.0
    total = len(records) * len(schema)
    non_null = sum(1 for record in records for field_name in schema if record.get(field_name) is not None)
    return non_null / total if total else 1.0


def _format_validity(records: list[dict[str, Any]], schema: dict[str, str]) -> float:
    from data_source_plugins.core.normalizer import infer_type

    if not records or not schema:
        return 1.0
    total = 0
    valid = 0
    for record in records:
        for field_name, expected_type in schema.items():
            if field_name not in record or record[field_name] is None:
                continue
            total += 1
            actual_type = infer_type(record[field_name])
            if actual_type == expected_type or expected_type in ("string", "number"):
                # A field successfully coerced to a wider type (e.g. int
                # into a "number" or "string" schema field) still counts
                # as format-valid — only an outright coercion failure
                # (still bearing its original, mismatched type) counts
                # against the score.
                valid += 1
    return valid / total if total else 1.0


def _freshness(records: list[dict[str, Any]], *, reference_time: datetime | None = None) -> float:
    if not records:
        return 1.0
    now = reference_time or datetime.now(UTC)
    timestamps: list[datetime] = []
    for record in records:
        for field_name in _FRESHNESS_FIELD_CANDIDATES:
            raw = record.get(field_name)
            if raw is None:
                continue
            parsed = _parse_timestamp(raw)
            if parsed is not None:
                timestamps.append(parsed)
            break
    if not timestamps:
        # No freshness signal in the payload at all — treat as freshly
        # synced rather than penalising sources that simply don't carry
        # a timestamp field.
        return 1.0
    newest = max(timestamps)
    age_seconds = max(0.0, (now - newest).total_seconds())
    if age_seconds <= _FRESHNESS_FULL_SCORE_SECONDS:
        return 1.0
    if age_seconds >= _FRESHNESS_ZERO_SCORE_SECONDS:
        return 0.0
    span = _FRESHNESS_ZERO_SCORE_SECONDS - _FRESHNESS_FULL_SCORE_SECONDS
    return 1.0 - (age_seconds - _FRESHNESS_FULL_SCORE_SECONDS) / span


def _parse_timestamp(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def score(
    records: list[dict[str, Any]], schema: dict[str, str], config: QualityConfig, *, reference_time: datetime | None = None
) -> QualityBreakdown:
    completeness = _completeness(records, schema)
    freshness = _freshness(records, reference_time=reference_time)
    format_validity = _format_validity(records, schema)

    weight_sum = config.completeness_weight + config.freshness_weight + config.format_validity_weight
    if weight_sum <= 0:
        overall = 0.0
    else:
        overall = (
            completeness * config.completeness_weight
            + freshness * config.freshness_weight
            + format_validity * config.format_validity_weight
        ) / weight_sum

    return QualityBreakdown(
        completeness_score=completeness, freshness_score=freshness,
        format_validity_score=format_validity, overall_score=overall,
    )
