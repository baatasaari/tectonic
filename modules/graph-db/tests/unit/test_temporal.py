from datetime import UTC, datetime, timedelta

from graph_db.core.domain import EdgeKind, EdgeRecord
from graph_db.core.temporal import is_valid_at


def _edge(valid_from: datetime, valid_to: datetime | None) -> EdgeRecord:
    return EdgeRecord(
        id="e1", tenant_id="t1", from_node_id="a", to_node_id="b", relationship_type="knows",
        edge_kind=EdgeKind.CORRELATIONAL, valid_from=valid_from, valid_to=valid_to,
    )


def test_currently_valid_edge_with_no_end():
    now = datetime.now(UTC)
    edge = _edge(now - timedelta(days=1), None)
    assert is_valid_at(edge, now) is True


def test_edge_not_yet_valid():
    now = datetime.now(UTC)
    edge = _edge(now + timedelta(days=1), None)
    assert is_valid_at(edge, now) is False


def test_edge_expired():
    now = datetime.now(UTC)
    edge = _edge(now - timedelta(days=10), now - timedelta(days=5))
    assert is_valid_at(edge, now) is False


def test_point_in_time_query_within_validity_window():
    edge = _edge(datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 6, 1, tzinfo=UTC))
    assert is_valid_at(edge, datetime(2024, 3, 1, tzinfo=UTC)) is True
    assert is_valid_at(edge, datetime(2023, 12, 1, tzinfo=UTC)) is False
    assert is_valid_at(edge, datetime(2024, 6, 1, tzinfo=UTC)) is False  # valid_to is exclusive
