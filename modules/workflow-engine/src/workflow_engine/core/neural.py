"""Neural Step Executor (LLD §2.2): invokes LLM/tool/agent calls for
ambiguous-judgement steps, calling out to the LLM Gateway module rather than
a model provider directly. Built on ADK `Agent`/`Task API` in production
(see NOTES.md "ADK integration" for how that plugs in behind this port);
here it drives the LLMGatewayClient/ToolOrchestrationClient/GuardrailsClient
ports so the module is fully testable stubbed, per the Deployability and
Testability Contract.
"""
from __future__ import annotations

from workflow_engine.core.domain import StepOutcome, StepStatus, WorkflowNode
from workflow_engine.core.ports import (
    AgenticRAGClient,
    GuardrailsClient,
    IntentDetectionClient,
    LLMGatewayClient,
    ToolOrchestrationClient,
)
from workflow_engine.telemetry.logging import get_logger

logger = get_logger(component="neural_executor")


class NeuralStepExecutor:
    def __init__(
        self,
        llm_gateway: LLMGatewayClient,
        tool_orchestration: ToolOrchestrationClient,
        guardrails: GuardrailsClient,
        intent_detection: IntentDetectionClient | None = None,
        agentic_rag: AgenticRAGClient | None = None,
    ) -> None:
        self.llm_gateway = llm_gateway
        self.tool_orchestration = tool_orchestration
        self.guardrails = guardrails
        # Optional: only steps configured with `config.intent_ref`/
        # `config.rag_ref` (see _execute_intent_step/_execute_rag_step below)
        # ever touch these — every pre-existing neural step (agent_ref-driven)
        # is completely unaffected, so both stay None (and every existing call
        # site of this constructor, positional, keeps working unchanged)
        # unless a caller wires a real client in (ticket #82).
        self.intent_detection = intent_detection
        self.agentic_rag = agentic_rag

    async def execute(
        self, node: WorkflowNode, context: dict, tenant_id: str, trace_id: str
    ) -> StepOutcome:
        intent_ref = node.config.get("intent_ref")
        if intent_ref:
            return await self._execute_intent_step(node, context, tenant_id)

        rag_ref = node.config.get("rag_ref")
        if rag_ref:
            return await self._execute_rag_step(node, context, tenant_id)

        agent_ref = node.config.get("agent_ref")
        if not agent_ref:
            return StepOutcome(status=StepStatus.FAILED, error="neural step missing config.agent_ref")

        allowed, decision = await self.guardrails.check(
            content={"input": context}, policy_profile=node.config.get("guardrails_profile", "default"), tenant_id=tenant_id
        )
        if not allowed:
            return StepOutcome(status=StepStatus.FAILED, error=f"guardrails blocked input: {decision}")

        response, confidence = await self.llm_gateway.complete(
            agent_ref=agent_ref, prompt_context=context, tenant_id=tenant_id, trace_id=trace_id
        )

        for tool_ref in node.config.get("tool_refs", []):
            tool_result = await self.tool_orchestration.invoke(
                tool_ref=tool_ref, arguments=response.get("tool_arguments", {}), tenant_id=tenant_id, trace_id=trace_id
            )
            response.setdefault("tool_results", {})[tool_ref] = tool_result

        allowed, decision = await self.guardrails.check(
            content={"output": response}, policy_profile=node.config.get("guardrails_profile", "default"), tenant_id=tenant_id
        )
        if not allowed:
            return StepOutcome(status=StepStatus.FAILED, error=f"guardrails blocked output: {decision}")

        return StepOutcome(status=StepStatus.COMPLETED, output=response, confidence_score=confidence)

    async def _execute_intent_step(self, node: WorkflowNode, context: dict, tenant_id: str) -> StepOutcome:
        """`config.intent_ref` marks a step as intent classification rather
        than an agent/tool call — a real call to Intent Detection (Module 5),
        not a routing table lookup. Deliberately bypasses guardrails/tool
        invocation entirely: classifying the raw user message is not itself
        an agent action with a side effect to screen, unlike an
        agent_ref-driven step's output."""
        if self.intent_detection is None:
            return StepOutcome(status=StepStatus.FAILED, error="intent step configured but no IntentDetectionClient wired")

        message = context.get("message", "")
        intent, confidence = await self.intent_detection.classify(message=message, tenant_id=tenant_id)
        return StepOutcome(status=StepStatus.COMPLETED, output={"intent": intent}, confidence_score=confidence)

    async def _execute_rag_step(self, node: WorkflowNode, context: dict, tenant_id: str) -> StepOutcome:
        """`config.rag_ref` marks a step as knowledge retrieval rather than
        an agent/tool call — a real call to Agentic RAG (Module 6), which
        itself retrieves from Knowledge Base/Vector DB for real. Deliberately
        bypasses guardrails/tool invocation, matching the intent step's own
        reasoning: retrieving knowledge is not itself an agent action with a
        side effect to screen."""
        if self.agentic_rag is None:
            return StepOutcome(status=StepStatus.FAILED, error="rag step configured but no AgenticRAGClient wired")

        message = context.get("message", "")
        result = await self.agentic_rag.retrieve(query=message, tenant_id=tenant_id)
        return StepOutcome(
            status=StepStatus.COMPLETED,
            output={
                "synthesized_context": result.get("synthesized_context", ""),
                "groundedness_score": result.get("groundedness_score", 0.0),
            },
            confidence_score=result.get("groundedness_score", 0.0),
        )
