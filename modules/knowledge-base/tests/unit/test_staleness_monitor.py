from datetime import UTC, datetime, timedelta

from knowledge_base.core.domain import DocumentRecord, DocumentStatus, SourceType, new_id
from knowledge_base.core.staleness_monitor import evaluate, is_stale


def _doc(days_since_review: int, status: DocumentStatus = DocumentStatus.ACTIVE, threshold_override: int | None = None) -> DocumentRecord:
    return DocumentRecord(
        id=new_id(), tenant_id="t1", title="doc", source_type=SourceType.UPLOAD, status=status,
        staleness_threshold_days=threshold_override,
        last_reviewed_at=datetime.now(UTC) - timedelta(days=days_since_review),
    )


def test_document_within_threshold_is_not_stale():
    doc = _doc(days_since_review=10)
    assert is_stale(doc, default_threshold_days=180) is False


def test_document_past_threshold_is_stale():
    doc = _doc(days_since_review=200)
    assert is_stale(doc, default_threshold_days=180) is True


def test_document_level_override_takes_precedence():
    doc = _doc(days_since_review=10, threshold_override=5)
    assert is_stale(doc, default_threshold_days=180) is True


def test_archived_documents_never_flagged_stale():
    doc = _doc(days_since_review=1000, status=DocumentStatus.ARCHIVED)
    assert is_stale(doc, default_threshold_days=180) is False


def test_evaluate_computes_ratio_excluding_archived():
    docs = [
        _doc(days_since_review=200),  # stale
        _doc(days_since_review=1),  # fresh
        _doc(days_since_review=1000, status=DocumentStatus.ARCHIVED),  # excluded
    ]
    report = evaluate(docs, default_threshold_days=180)
    assert len(report.stale_document_ids) == 1
    assert report.total_active_or_stale == 2
    assert report.stale_ratio == 0.5


def test_evaluate_empty_list_zero_ratio():
    report = evaluate([], default_threshold_days=180)
    assert report.stale_ratio == 0.0
