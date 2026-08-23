from workflow_engine.core.domain import ExecutionMode, RetryPolicy, WorkflowNode
from workflow_engine.core.router import resolve_execution_mode


def _node(execution_mode: ExecutionMode, config: dict | None = None) -> WorkflowNode:
    return WorkflowNode(
        id="s1", type="task", execution_mode=execution_mode, config=config or {}, retry_policy=RetryPolicy()
    )


def test_explicit_mode_is_used_as_is():
    assert resolve_execution_mode(_node(ExecutionMode.SYMBOLIC)) == ExecutionMode.SYMBOLIC
    assert resolve_execution_mode(_node(ExecutionMode.NEURAL)) == ExecutionMode.NEURAL
    assert resolve_execution_mode(_node(ExecutionMode.HUMAN)) == ExecutionMode.HUMAN


def test_auto_with_symbolic_rule_ref_resolves_symbolic():
    node = _node(ExecutionMode.AUTO, {"symbolic_rule_ref": "r1"})
    assert resolve_execution_mode(node) == ExecutionMode.SYMBOLIC


def test_auto_without_symbolic_rule_ref_resolves_neural():
    node = _node(ExecutionMode.AUTO, {"agent_ref": "a1"})
    assert resolve_execution_mode(node) == ExecutionMode.NEURAL
