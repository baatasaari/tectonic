from datetime import UTC, datetime, timedelta

from data_source_plugins.config import QualityConfig
from data_source_plugins.core.quality_scorer import score


def test_fully_complete_records_score_completeness_one():
    records = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    schema = {"id": "integer", "name": "string"}
    breakdown = score(records, schema, QualityConfig())
    assert breakdown.completeness_score == 1.0


def test_missing_fields_reduce_completeness():
    records = [{"id": 1, "name": None}, {"id": 2, "name": "b"}]
    schema = {"id": "integer", "name": "string"}
    breakdown = score(records, schema, QualityConfig())
    assert breakdown.completeness_score == 0.75  # 3 of 4 (record, field) pairs non-null


def test_stale_timestamp_reduces_freshness():
    old = datetime.now(UTC) - timedelta(days=10)
    records = [{"id": 1, "updated_at": old.isoformat()}]
    schema = {"id": "integer", "updated_at": "string"}
    breakdown = score(records, schema, QualityConfig(), reference_time=datetime.now(UTC))
    assert breakdown.freshness_score == 0.0


def test_fresh_timestamp_scores_freshness_one():
    recent = datetime.now(UTC) - timedelta(minutes=5)
    records = [{"id": 1, "updated_at": recent.isoformat()}]
    schema = {"id": "integer", "updated_at": "string"}
    breakdown = score(records, schema, QualityConfig(), reference_time=datetime.now(UTC))
    assert breakdown.freshness_score == 1.0


def test_no_records_scores_perfectly_by_convention():
    breakdown = score([], {"id": "integer"}, QualityConfig())
    assert breakdown.overall_score == 1.0


def test_overall_score_is_weighted_average():
    config = QualityConfig(completeness_weight=1.0, freshness_weight=0.0, format_validity_weight=0.0)
    records = [{"id": 1, "name": None}, {"id": 2, "name": "b"}]
    schema = {"id": "integer", "name": "string"}
    breakdown = score(records, schema, config)
    assert breakdown.overall_score == breakdown.completeness_score
