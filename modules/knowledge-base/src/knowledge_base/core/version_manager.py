"""Version Manager (LLD §2 sub-components): content-addressed storage
(hash-based) plus explicit version metadata, so near-duplicate revisions
dedup cheaply and lineage stays clear.
"""
from __future__ import annotations

import hashlib

from knowledge_base.core.domain import DocumentVersionRecord


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def next_version_number(existing_versions: list[DocumentVersionRecord]) -> int:
    if not existing_versions:
        return 1
    return max(v.version_number for v in existing_versions) + 1
