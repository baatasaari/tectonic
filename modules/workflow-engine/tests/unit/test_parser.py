import pytest

from workflow_engine.core.parser import GraphValidationError, parse_and_validate


def _valid_schema() -> dict:
    return {
        "nodes": [
            {"id": "step_1", "execution_mode": "symbolic", "config": {"symbolic_rule_ref": "r1"}},
            {"id": "step_2", "execution_mode": "neural", "config": {"agent_ref": "a1"}},
        ],
        "edges": [{"from": "step_1", "to": "step_2"}],
        "entry_point": "step_1",
        "termination_points": ["step_2"],
    }


def test_valid_graph_parses():
    graph = parse_and_validate(_valid_schema())
    assert graph.entry_point == "step_1"
    assert graph.termination_points == ["step_2"]
    assert {n.id for n in graph.nodes} == {"step_1", "step_2"}
    assert graph.outgoing("step_1")[0].to == "step_2"


def test_unknown_entry_point_rejected():
    schema = _valid_schema()
    schema["entry_point"] = "nope"
    with pytest.raises(GraphValidationError) as exc:
        parse_and_validate(schema)
    assert any("entry_point" in e for e in exc.value.errors)


def test_dead_end_rejected():
    schema = _valid_schema()
    schema["nodes"].append({"id": "step_3", "execution_mode": "neural", "config": {"agent_ref": "a2"}})
    # step_3 has no outgoing edge and isn't a termination point.
    with pytest.raises(GraphValidationError) as exc:
        parse_and_validate(schema)
    assert any("dead end" in e for e in exc.value.errors)


def test_unreachable_node_rejected():
    schema = _valid_schema()
    schema["nodes"].append({"id": "step_3", "execution_mode": "neural", "config": {"agent_ref": "a2"}})
    schema["termination_points"].append("step_3")
    with pytest.raises(GraphValidationError) as exc:
        parse_and_validate(schema)
    assert any("unreachable" in e for e in exc.value.errors)


def test_cycle_without_loop_type_rejected():
    schema = _valid_schema()
    schema["edges"].append({"from": "step_2", "to": "step_1"})
    with pytest.raises(GraphValidationError) as exc:
        parse_and_validate(schema)
    assert any("cycle" in e for e in exc.value.errors)


def test_cycle_with_loop_type_allowed():
    schema = _valid_schema()
    schema["nodes"][1]["type"] = "loop"
    schema["edges"].append({"from": "step_2", "to": "step_1"})
    graph = parse_and_validate(schema)
    assert len(graph.edges) == 2


def test_duplicate_node_ids_rejected():
    schema = _valid_schema()
    schema["nodes"].append({"id": "step_1", "execution_mode": "neural", "config": {}})
    with pytest.raises(GraphValidationError):
        parse_and_validate(schema)


def test_edge_to_unknown_node_rejected():
    schema = _valid_schema()
    schema["edges"].append({"from": "step_2", "to": "ghost"})
    with pytest.raises(GraphValidationError) as exc:
        parse_and_validate(schema)
    assert any("unknown target" in e for e in exc.value.errors)
