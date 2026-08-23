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
from workflow_engine.core.ports import GuardrailsClient, LLMGatewayClient, ToolOrchestrationClient
from workflow_engine.telemetry.logging import get_logger

logger = get_logger(component="neural_executor")


class NeuralStepExecutor:
    def __init__(
        self,
        llm_gateway: LLMGatewayClient,
        tool_orchestration: ToolOrchestrationClient,
        guardrails: GuardrailsClient,
    ) -> None:
        self.llm_gateway = llm_gateway
        self.tool_orchestration = tool_orchestration
        self.guardrails = guardrails

    async def execute(
        self, node: WorkflowNode, context: dict, tenant_id: str, trace_id: str
    ) -> StepOutcome:
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
