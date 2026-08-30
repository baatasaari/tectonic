import pytest

from graph_db.core.causal_validator import validate_edge_kind
from graph_db.core.domain import EdgeKind, InvalidEdgeKindError, MissingEdgeKindError


def test_valid_kinds_accepted():
    assert validate_edge_kind("causal") == EdgeKind.CAUSAL
    assert validate_edge_kind("correlational") == EdgeKind.CORRELATIONAL
    assert validate_edge_kind("structural") == EdgeKind.STRUCTURAL


def test_missing_edge_kind_rejected():
    with pytest.raises(MissingEdgeKindError):
        validate_edge_kind(None)
    with pytest.raises(MissingEdgeKindError):
        validate_edge_kind("")


def test_invalid_edge_kind_rejected():
    with pytest.raises(InvalidEdgeKindError):
        validate_edge_kind("maybe")
