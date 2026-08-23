"""Access Policy Tagger (LLD §2 sub-components): applies policy tags at
chunk level, inheriting the document-level policy by default with an
explicit chunk-level override taking precedence — the LLD's differentiator
over document-only access control.
"""
from __future__ import annotations


def tag_chunks(
    chunk_count: int, document_policy_tags: list[str], chunk_overrides: dict[int, list[str]] | None = None,
) -> list[list[str]]:
    overrides = chunk_overrides or {}
    return [list(overrides[i]) if i in overrides else list(document_policy_tags) for i in range(chunk_count)]
