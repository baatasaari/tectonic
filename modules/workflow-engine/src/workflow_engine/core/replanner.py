"""Replanner (LLD §2.2, §3.5): structural and content adaptation on step
failure. A symbolic planner decides the structural change (which alternative
step, if any, the graph reroutes to); the Neural Step Executor's LLM Gateway
call adapts that alternative step's content to the failure context. Purely
symbolic + neural collaboration — no separate "planning" model call, keeping
the structural decision deterministic and explainable per the module's
neurosymbolic design.
"""
from __future__ import annotations

from workflow_engine.core.domain import ReplanEventRecord, WorkflowGraph, WorkflowNode, new_id
from workflow_engine.core.ports import LLMGatewayClient, WorkflowRepository


class Replanner:
    def __init__(self, repository: WorkflowRepository, llm_gateway: LLMGatewayClient) -> None:
        self.repository = repository
        self.llm_gateway = llm_gateway

    def find_structural_alternative(self, graph: WorkflowGraph, failed_step_id: str) -> WorkflowNode | None:
        """Symbolic planner: a node may declare `config.replan_fallback_step_id`
        naming the step to reroute to on unrecoverable failure. Deterministic
        lookup — no inference, so the structural decision stays explainable."""
        failed_node = graph.node(failed_step_id)
        fallback_id = failed_node.config.get("replan_fallback_step_id")
        if not fallback_id:
            return None
        try:
            return graph.node(fallback_id)
        except KeyError:
            return None

    async def replan(
        self,
        *,
        instance_id: str,
        graph: WorkflowGraph,
        failed_step_id: str,
        reason: str,
        context: dict,
        tenant_id: str,
        trace_id: str,
    ) -> tuple[ReplanEventRecord | None, WorkflowNode | None]:
        alternative = self.find_structural_alternative(graph, failed_step_id)
        if alternative is None:
            return None, None

        adapted_content, _confidence = await self.llm_gateway.complete(
            agent_ref=alternative.config.get("agent_ref", "replan-content-adapter"),
            prompt_context={"failure_reason": reason, "original_step": failed_step_id, **context},
            tenant_id=tenant_id,
            trace_id=trace_id,
        )

        graph_delta = {
            "reroute_from": failed_step_id,
            "reroute_to": alternative.id,
            "adapted_content": adapted_content,
        }
        record = ReplanEventRecord(
            id=new_id(),
            instance_id=instance_id,
            trigger_reason=reason,
            original_step_id=failed_step_id,
            new_graph_delta=graph_delta,
        )
        record = await self.repository.create_replan_event(record)
        return record, alternative
