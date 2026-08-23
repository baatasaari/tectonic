"""Tool Synthesis Engine (LLD §2.2, differentiator: "just-in-time tool
synthesis"). Composes a new tool from existing primitives for narrow,
well-specified gaps — gated so this stays a safe capability, not an open
door: an LLM Gateway call proposes the composition, Guardrails checks the
proposal, and a Sentinel Agent review is always required before the tool
can ever reach `active` status. This engine never sets status=active
itself — only `/tools/{id}/approve` (LLD §3.3) does that, after a recorded
Guardrails pass and a Sentinel review.
"""
from __future__ import annotations

from tool_orchestration.config import SynthesisConfig
from tool_orchestration.core.domain import (
    SynthesisRejectedError,
    ToolDefinitionRecord,
    ToolStatus,
    new_id,
)
from tool_orchestration.core.ports import (
    GuardrailsClient,
    LLMGatewayClient,
    SentinelAgentsClient,
    ToolRepository,
)
from tool_orchestration.telemetry.metrics import tool_synthesis_requests_total


class ToolSynthesisEngine:
    def __init__(
        self,
        repository: ToolRepository,
        llm_gateway: LLMGatewayClient,
        guardrails: GuardrailsClient,
        sentinel: SentinelAgentsClient,
        config: SynthesisConfig,
    ) -> None:
        self.repository = repository
        self.llm_gateway = llm_gateway
        self.guardrails = guardrails
        self.sentinel = sentinel
        self.config = config

    async def synthesise(
        self, *, gap_description: str, available_primitives: list[str], tenant_id: str
    ) -> ToolDefinitionRecord:
        if not self.config.enabled:
            tool_synthesis_requests_total.labels(tenant_id=tenant_id, outcome="rejected").inc()
            raise SynthesisRejectedError("tool synthesis is disabled for this tenant")

        proposal = await self.llm_gateway.complete(
            prompt_context={"gap_description": gap_description, "available_primitives": available_primitives},
            tenant_id=tenant_id,
        )

        allowed, decision = await self.guardrails.check(
            content={"proposal": proposal}, policy_profile="tool_synthesis", tenant_id=tenant_id
        )
        if not allowed:
            tool_synthesis_requests_total.labels(tenant_id=tenant_id, outcome="rejected").inc()
            raise SynthesisRejectedError(f"guardrails blocked synthesised tool proposal: {decision}")

        record = ToolDefinitionRecord(
            id=new_id(),
            tenant_id=tenant_id,
            name=proposal.get("name", f"synthesised-{new_id()[:8]}"),
            mcp_server_ref=proposal.get("mcp_server_ref", "synthesised"),
            schema=proposal.get("schema", {}),
            status=ToolStatus.PENDING_REVIEW,
            synthesised=True,
        )
        record = await self.repository.create_tool_definition(record)

        # require_sentinel_approval cannot be False while synthesis is
        # enabled (enforced at config load — see config.py), so this call
        # always happens for a synthesised tool.
        await self.sentinel.submit_for_review(tool_id=record.id, proposed_schema=record.schema, tenant_id=tenant_id)

        tool_synthesis_requests_total.labels(tenant_id=tenant_id, outcome="pending_review").inc()
        return record
