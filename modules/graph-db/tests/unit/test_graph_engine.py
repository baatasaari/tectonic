from datetime import UTC, datetime, timedelta

import pytest

from graph_db.core.domain import MissingEdgeKindError


async def _make_chain(harness, length: int, edge_kind: str = "correlational"):
    """Creates a linear chain of `length` nodes: n0 -> n1 -> ... -> n(length-1)."""
    nodes = []
    for i in range(length):
        n = await harness.engine.write_node(tenant_id="t1", entity_type="thing", name=f"n{i}", attributes={})
        nodes.append(n)
    for i in range(length - 1):
        await harness.engine.write_edge(
            tenant_id="t1", from_node_id=nodes[i].id, to_node_id=nodes[i + 1].id,
            relationship_type="next", edge_kind=edge_kind, source_ref="test",
        )
    return nodes


async def test_write_node_and_get(harness):
    node = await harness.engine.write_node(tenant_id="t1", entity_type="person", name="Alice", attributes={"age": 30})
    fetched = await harness.repository.get_node("t1", node.id)
    assert fetched.name == "Alice"
    assert fetched.attributes == {"age": 30}


async def test_write_edge_requires_edge_kind(harness):
    a = await harness.engine.write_node(tenant_id="t1", entity_type="thing", name="A", attributes={})
    b = await harness.engine.write_node(tenant_id="t1", entity_type="thing", name="B", attributes={})
    with pytest.raises(MissingEdgeKindError):
        await harness.engine.write_edge(
            tenant_id="t1", from_node_id=a.id, to_node_id=b.id, relationship_type="rel", edge_kind=None,
        )


async def test_write_node_and_edge_emit_audit_events(harness):
    a = await harness.engine.write_node(tenant_id="t1", entity_type="thing", name="A", attributes={})
    b = await harness.engine.write_node(tenant_id="t1", entity_type="thing", name="B", attributes={})
    await harness.engine.write_edge(
        tenant_id="t1", from_node_id=a.id, to_node_id=b.id, relationship_type="rel", edge_kind="causal",
    )
    kinds = [e["event"] for e in harness.auditability.events]
    assert kinds.count("node_created") == 2
    assert kinds.count("edge_created") == 1


async def test_neighbours_bfs_respects_depth(harness):
    nodes = await _make_chain(harness, 5)  # n0-n1-n2-n3-n4
    subgraph = await harness.engine.neighbours("t1", nodes[0].id, depth=2)
    found_names = {n.name for n in subgraph.nodes}
    assert found_names == {"n0", "n1", "n2"}


async def test_neighbours_capped_by_max_depth_config(harness_factory):
    harness = harness_factory(max_depth=1)
    nodes = await _make_chain(harness, 5)
    subgraph = await harness.engine.neighbours("t1", nodes[0].id, depth=10)
    found_names = {n.name for n in subgraph.nodes}
    assert found_names == {"n0", "n1"}


async def test_neighbours_traverses_both_directions(harness):
    a = await harness.engine.write_node(tenant_id="t1", entity_type="thing", name="A", attributes={})
    b = await harness.engine.write_node(tenant_id="t1", entity_type="thing", name="B", attributes={})
    await harness.engine.write_edge(
        tenant_id="t1", from_node_id=b.id, to_node_id=a.id, relationship_type="rel", edge_kind="causal",
    )
    subgraph = await harness.engine.neighbours("t1", a.id, depth=1)
    assert {n.id for n in subgraph.nodes} == {a.id, b.id}


async def test_neighbours_filters_by_edge_kind(harness):
    a = await harness.engine.write_node(tenant_id="t1", entity_type="thing", name="A", attributes={})
    b = await harness.engine.write_node(tenant_id="t1", entity_type="thing", name="B", attributes={})
    c = await harness.engine.write_node(tenant_id="t1", entity_type="thing", name="C", attributes={})
    await harness.engine.write_edge(
        tenant_id="t1", from_node_id=a.id, to_node_id=b.id, relationship_type="rel", edge_kind="causal",
    )
    await harness.engine.write_edge(
        tenant_id="t1", from_node_id=a.id, to_node_id=c.id, relationship_type="rel", edge_kind="correlational",
    )
    subgraph = await harness.engine.neighbours("t1", a.id, depth=1, edge_kind_filter="causal")
    names = {n.name for n in subgraph.nodes}
    assert names == {"A", "B"}


async def test_neighbours_respects_temporal_as_of(harness):
    a = await harness.engine.write_node(tenant_id="t1", entity_type="thing", name="A", attributes={})
    b = await harness.engine.write_node(tenant_id="t1", entity_type="thing", name="B", attributes={})
    now = datetime.now(UTC)
    await harness.engine.write_edge(
        tenant_id="t1", from_node_id=a.id, to_node_id=b.id, relationship_type="rel", edge_kind="causal",
        valid_from=now - timedelta(days=10), valid_to=now - timedelta(days=5),
    )
    subgraph_now = await harness.engine.neighbours("t1", a.id, depth=1, as_of=now)
    assert {n.name for n in subgraph_now.nodes} == {"A"}

    subgraph_past = await harness.engine.neighbours("t1", a.id, depth=1, as_of=now - timedelta(days=7))
    assert {n.name for n in subgraph_past.nodes} == {"A", "B"}


async def test_path_finds_shortest_route(harness):
    nodes = await _make_chain(harness, 4)  # n0-n1-n2-n3
    subgraph = await harness.engine.path("t1", nodes[0].id, nodes[3].id, depth=5)
    assert subgraph.node_path == [nodes[0].id, nodes[1].id, nodes[2].id, nodes[3].id]
    assert len(subgraph.edges) == 3


async def test_path_same_node_returns_single_node_path(harness):
    a = await harness.engine.write_node(tenant_id="t1", entity_type="thing", name="A", attributes={})
    subgraph = await harness.engine.path("t1", a.id, a.id, depth=3)
    assert subgraph.node_path == [a.id]
    assert subgraph.edges == []


async def test_path_no_route_within_depth_returns_empty(harness):
    nodes = await _make_chain(harness, 5)
    subgraph = await harness.engine.path("t1", nodes[0].id, nodes[4].id, depth=2)
    assert subgraph.node_path == []
    assert subgraph.nodes == []


async def test_path_unreachable_target_returns_empty(harness):
    a = await harness.engine.write_node(tenant_id="t1", entity_type="thing", name="A", attributes={})
    b = await harness.engine.write_node(tenant_id="t1", entity_type="thing", name="B", attributes={})
    subgraph = await harness.engine.path("t1", a.id, b.id, depth=5)
    assert subgraph.node_path == []
