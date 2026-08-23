"""Step Router (LLD §2.2): classifies each step symbolic/neural/human at runtime.

`execution_mode=auto` resolves to `symbolic` when the node carries a
`symbolic_rule_ref`, otherwise `neural`. `human` is never inferred — a step
only routes to the Human Approval Handler directly when explicitly configured
that way, or when a neural step's confidence falls below its threshold (that
escalation is decided by the Neural Step Executor, not the router).
"""
from __future__ import annotations

from workflow_engine.core.domain import ExecutionMode, WorkflowNode


def resolve_execution_mode(node: WorkflowNode) -> ExecutionMode:
    if node.execution_mode != ExecutionMode.AUTO:
        return node.execution_mode
    if node.config.get("symbolic_rule_ref"):
        return ExecutionMode.SYMBOLIC
    return ExecutionMode.NEURAL
