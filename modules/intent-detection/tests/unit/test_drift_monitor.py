from intent_detection.core.domain import (
    ClassificationLogRecord,
    DetectedIntent,
    IntentDefinition,
    IntentTaxonomyRecord,
    TaxonomyStatus,
    new_id,
)
from intent_detection.core.drift_monitor import DriftMonitor


def _taxonomy() -> IntentTaxonomyRecord:
    return IntentTaxonomyRecord(
        id="t1", tenant_id="tenant-a", version=1, status=TaxonomyStatus.ACTIVE,
        intents=[
            IntentDefinition(name="a", examples=["x", "y"]),  # 2 examples
            IntentDefinition(name="b", examples=["z"]),        # 1 example
        ],
    )


def _log(intent_name: str) -> ClassificationLogRecord:
    return ClassificationLogRecord(
        id=new_id(), tenant_id="tenant-a", input_hash="h", taxonomy_version=1,
        intents_detected=[DetectedIntent(name=intent_name, confidence=0.9)], fallback_used=False,
    )


def test_no_drift_when_observed_matches_baseline_shape():
    taxonomy = _taxonomy()
    # baseline: a=2/3, b=1/3 -> approximate with 2 "a" logs, 1 "b" log
    logs = [_log("a"), _log("a"), _log("b")]
    report = DriftMonitor().compute_report("tenant-a", taxonomy, logs, alert_threshold=0.15)
    assert report.drift_score < 0.05
    assert report.flagged_intents == []


def test_drift_flagged_when_observed_diverges_sharply():
    taxonomy = _taxonomy()
    # baseline strongly favors "a" (2/3), but all traffic is "b".
    logs = [_log("b")] * 10
    report = DriftMonitor().compute_report("tenant-a", taxonomy, logs, alert_threshold=0.15)
    assert report.drift_score > 0.15
    assert "b" in report.flagged_intents or "a" in report.flagged_intents


def test_unseen_intent_in_traffic_is_flagged():
    taxonomy = _taxonomy()
    logs = [_log("totally_new_intent")] * 5
    report = DriftMonitor().compute_report("tenant-a", taxonomy, logs, alert_threshold=0.15)
    assert "totally_new_intent" in report.flagged_intents


def test_empty_logs_produces_zero_drift():
    taxonomy = _taxonomy()
    report = DriftMonitor().compute_report("tenant-a", taxonomy, [], alert_threshold=0.15)
    assert report.drift_score == 0.0
