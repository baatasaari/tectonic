from knowledge_base.core.domain import DocumentVersionRecord, new_id
from knowledge_base.core.version_manager import content_hash, next_version_number


def test_content_hash_deterministic():
    assert content_hash(b"hello") == content_hash(b"hello")


def test_content_hash_differs_for_different_content():
    assert content_hash(b"hello") != content_hash(b"world")


def test_next_version_number_starts_at_one():
    assert next_version_number([]) == 1


def test_next_version_number_increments_from_max():
    versions = [
        DocumentVersionRecord(id=new_id(), document_id="d1", content_hash="a", blob_ref="a", version_number=1),
        DocumentVersionRecord(id=new_id(), document_id="d1", content_hash="b", blob_ref="b", version_number=3),
    ]
    assert next_version_number(versions) == 4
