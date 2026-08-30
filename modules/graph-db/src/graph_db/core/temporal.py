"""Temporal Filter (LLD §2 sub-components): applies valid-from/valid-to
filtering for point-in-time queries.
"""
from __future__ import annotations

from datetime import datetime

from graph_db.core.domain import EdgeRecord


def is_valid_at(edge: EdgeRecord, as_of: datetime) -> bool:
    if edge.valid_from > as_of:
        return False
    return edge.valid_to is None or edge.valid_to > as_of
