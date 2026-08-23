"""Eval Library Adapters + Domain-Specific Metrics (LLD §2 sub-components).

The LLD calls for wrapping DeepEval, Ragas and an OpenAI-Evals-compatible
format behind one unified interface, with custom financial/domain metrics
ported directly from the (external, not-available-here) AgentEval
project. DeepEval and Ragas pull in heavy dependency trees (torch,
transformer model downloads) unsuited to this module's offline unit-test
tier, and AgentEval's source isn't available in this build environment —
so this module implements its own lightweight metric functions behind
the same `EvalMetric` protocol a real DeepEval/Ragas/AgentEval adapter
would satisfy, falling back to an LLM Gateway LLM-as-judge call
(`core/ports.py`'s `LLMGatewayClient.judge`) for any metric name it
doesn't have a local heuristic for. Swapping in a real library later is a
matter of adding another `EvalMetric` implementation, not restructuring
the orchestrator.
"""
from __future__ import annotations

import re
from typing import Any, Protocol

from evaluation_framework.core.ports import LLMGatewayClient
from evaluation_framework.core.similarity import cosine_similarity, tokenize


class EvalMetric(Protocol):
    async def compute(self, agent_output: str, reference_data: dict[str, Any], llm_gateway: LLMGatewayClient) -> float: ...


class FaithfulnessMetric:
    """Term-overlap cosine similarity between the agent output and
    `reference_data["context"]` — the same lightweight approach Guardrails'
    Groundedness Checker uses for the same underlying question (is this text
    supported by this context?)."""

    async def compute(self, agent_output: str, reference_data: dict[str, Any], llm_gateway: LLMGatewayClient) -> float:
        context = reference_data.get("context", "")
        if not context:
            return 0.0
        return cosine_similarity(tokenize(agent_output), tokenize(context))


_SENTENCE_RE = re.compile(r"[.!?]+")


class CoherenceMetric:
    """A deliberately simple redundancy/repetition heuristic — not a real
    coherence model: penalises degenerate output (repeated sentences,
    heavy word repetition), which is the failure mode this metric can
    actually detect without a trained model. Score is unique-token ratio
    weighted by unique-sentence ratio."""

    async def compute(self, agent_output: str, reference_data: dict[str, Any], llm_gateway: LLMGatewayClient) -> float:
        tokens = tokenize(agent_output)
        if not tokens:
            return 0.0
        unique_token_ratio = len(tokens) / sum(tokens.values())

        sentences = [s.strip() for s in _SENTENCE_RE.split(agent_output) if s.strip()]
        if not sentences:
            return unique_token_ratio
        unique_sentence_ratio = len(set(sentences)) / len(sentences)

        return min(1.0, unique_token_ratio * unique_sentence_ratio * 1.3)


class ToolTraceCorrectnessMetric:
    """Fraction of tool calls in `reference_data["actual_tool_sequence"]`
    (a list of `{"tool": str, "status": str}`) that did not error. No tool
    calls recorded is treated as trivially correct (nothing to get wrong)."""

    async def compute(self, agent_output: str, reference_data: dict[str, Any], llm_gateway: LLMGatewayClient) -> float:
        trace = reference_data.get("actual_tool_sequence", [])
        if not trace:
            return 1.0
        ok = sum(1 for call in trace if call.get("status") != "error")
        return ok / len(trace)


_DISCLAIMER_PATTERNS = ("not financial advice", "not investment advice", "consult a qualified", "past performance")
_GUARANTEE_PATTERNS = ("guaranteed return", "guaranteed profit", "risk-free return", "cannot lose")


class FinancialGuidanceComplianceMetric:
    """Domain-specific pack (LLD: "financial guidance compliance...built on
    the same foundation as your own AgentEval work" — reimplemented here
    since that codebase isn't available in this build environment).
    Checks for a disclaimer and the absence of guaranteed-return language."""

    async def compute(self, agent_output: str, reference_data: dict[str, Any], llm_gateway: LLMGatewayClient) -> float:
        text = agent_output.lower()
        has_disclaimer = any(p in text for p in _DISCLAIMER_PATTERNS)
        has_guarantee_claim = any(p in text for p in _GUARANTEE_PATTERNS)
        if has_guarantee_claim:
            return 0.0
        return 1.0 if has_disclaimer else 0.5


class LLMJudgeMetric:
    """Fallback for any metric name not covered by a local heuristic."""

    def __init__(self, metric_name: str) -> None:
        self._metric_name = metric_name

    async def compute(self, agent_output: str, reference_data: dict[str, Any], llm_gateway: LLMGatewayClient) -> float:
        return await llm_gateway.judge(agent_output, self._metric_name, reference_data)


_REGISTRY: dict[str, EvalMetric] = {
    "faithfulness": FaithfulnessMetric(),
    "coherence": CoherenceMetric(),
    "tool_trace_correctness": ToolTraceCorrectnessMetric(),
    "financial_guidance_compliance": FinancialGuidanceComplianceMetric(),
}


def resolve_metric(metric_name: str) -> EvalMetric:
    return _REGISTRY.get(metric_name, LLMJudgeMetric(metric_name))
