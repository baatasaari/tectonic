"""Definition Parser/Validator (LLD §2.2, §3.2).

Parses the platform-level workflow schema into the internal `WorkflowGraph`
domain representation and validates it: schema shape (via Pydantic), cycles
(via networkx, `loop`-typed nodes excepted), dead ends, and edge/entry/
termination references.

This keeps the platform-level schema (`execution_mode`, `confidence_threshold`,
`approval_policy_ref`, tenant scoping) a stable public contract independent of
whatever graph representation the underlying workflow runtime (ADK 2.0's
Workflow Runtime in production) uses internally.
"""
from __future__ import annotations

import networkx as nx
from pydantic import BaseModel, Field, field_validator

from workflow_engine.core.domain import (
    ExecutionMode,
    RetryPolicy,
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
)


class GraphValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class RetryPolicySchema(BaseModel):
    max_retries: int = 3
    backoff_strategy: str = "exponential"
    compensation_step_id: str | None = None


class NodeSchema(BaseModel):
    id: str
    type: str = "task"
    execution_mode: ExecutionMode = ExecutionMode.AUTO
    confidence_threshold: float = Field(0.85, ge=0.0, le=1.0)
    config: dict = Field(default_factory=dict)
    retry_policy: RetryPolicySchema = RetryPolicySchema()
    timeout_seconds: int = 30


class EdgeSchema(BaseModel):
    from_: str = Field(alias="from")
    to: str
    condition: str | None = None

    model_config = {"populate_by_name": True}


class GraphSchema(BaseModel):
    nodes: list[NodeSchema]
    edges: list[EdgeSchema] = Field(default_factory=list)
    entry_point: str
    termination_points: list[str]

    @field_validator("nodes")
    @classmethod
    def _unique_node_ids(cls, nodes: list[NodeSchema]) -> list[NodeSchema]:
        ids = [n.id for n in nodes]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate node ids: {sorted(dupes)}")
        return nodes


def parse_and_validate(raw_schema: dict) -> WorkflowGraph:
    """Raises GraphValidationError on any structural problem; otherwise
    returns the internal WorkflowGraph ready for scheduling."""
    errors: list[str] = []

    try:
        schema = GraphSchema.model_validate(raw_schema)
    except Exception as e:  # pydantic ValidationError
        raise GraphValidationError([str(e)]) from e

    node_ids = {n.id for n in schema.nodes}

    if schema.entry_point not in node_ids:
        errors.append(f"entry_point '{schema.entry_point}' is not a defined node")

    for tp in schema.termination_points:
        if tp not in node_ids:
            errors.append(f"termination_point '{tp}' is not a defined node")

    for e in schema.edges:
        if e.from_ not in node_ids:
            errors.append(f"edge references unknown source node '{e.from_}'")
        if e.to not in node_ids:
            errors.append(f"edge references unknown target node '{e.to}'")

    g = nx.DiGraph()
    g.add_nodes_from(node_ids)
    g.add_edges_from((e.from_, e.to) for e in schema.edges if e.from_ in node_ids and e.to in node_ids)

    # Cycle detection: allow a cycle only if at least one node on it is
    # explicitly typed "loop" — the loop-controller node that decides
    # whether the cycle repeats or exits (ADK 2.0 Workflow Runtime supports
    # loop nodes natively). An untagged cycle is almost always an authoring
    # mistake, not an intentional loop.
    for cycle in nx.simple_cycles(g):
        if not any(_node_type(schema, nid) == "loop" for nid in cycle):
            errors.append(f"cycle detected without a loop-typed node: {cycle}")

    # Nodes only ever reached via an exceptional path (compensation on retry
    # exhaustion, or the replanner's structural fallback) are not wired into
    # the normal edge flow by design — they're excluded from the dead-end
    # and reachability checks below rather than forced into the DAG.
    exceptional_path_nodes = {
        n.retry_policy.compensation_step_id for n in schema.nodes if n.retry_policy.compensation_step_id
    } | {n.config.get("replan_fallback_step_id") for n in schema.nodes if n.config.get("replan_fallback_step_id")}

    # Dead-end detection: every non-termination, non-exceptional-path node
    # must have at least one outgoing edge, and every non-entry,
    # non-exceptional-path node must be reachable from entry.
    termination_set = set(schema.termination_points)
    for nid in node_ids:
        if nid in termination_set or nid in exceptional_path_nodes:
            continue
        if g.out_degree(nid) == 0:
            errors.append(f"node '{nid}' is a dead end (no outgoing edge, not a termination point)")

    if schema.entry_point in g:
        reachable = nx.descendants(g, schema.entry_point) | {schema.entry_point}
        unreachable = node_ids - reachable - exceptional_path_nodes
        if unreachable:
            errors.append(f"unreachable nodes from entry_point: {sorted(unreachable)}")

    if errors:
        raise GraphValidationError(errors)

    nodes = [
        WorkflowNode(
            id=n.id,
            type=n.type,
            execution_mode=n.execution_mode,
            confidence_threshold=n.confidence_threshold,
            config=n.config,
            retry_policy=RetryPolicy(
                max_retries=n.retry_policy.max_retries,
                backoff_strategy=n.retry_policy.backoff_strategy,
                compensation_step_id=n.retry_policy.compensation_step_id,
            ),
            timeout_seconds=n.timeout_seconds,
        )
        for n in schema.nodes
    ]
    edges = [WorkflowEdge(from_=e.from_, to=e.to, condition=e.condition) for e in schema.edges]
    return WorkflowGraph(
        nodes=nodes, edges=edges, entry_point=schema.entry_point, termination_points=schema.termination_points
    )


def _node_type(schema: GraphSchema, node_id: str) -> str:
    for n in schema.nodes:
        if n.id == node_id:
            return n.type
    return ""
