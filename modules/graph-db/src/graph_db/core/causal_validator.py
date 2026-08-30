"""Causal Edge Validator (LLD §2 sub-components): enforces that edges are
explicitly typed as causal/correlational/structural at write time,
rejects untyped edges (LLD §Level 3 "Sequence: causal-typed edge write").
"""
from __future__ import annotations

from graph_db.core.domain import EdgeKind, InvalidEdgeKindError, MissingEdgeKindError


def validate_edge_kind(raw: str | None) -> EdgeKind:
    if raw is None or raw == "":
        raise MissingEdgeKindError()
    try:
        return EdgeKind(raw)
    except ValueError as e:
        raise InvalidEdgeKindError(raw) from e
