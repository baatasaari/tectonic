"""Eval Library Adapters + Domain-Specific Metrics (LLD §2 sub-components).

The LLD calls for wrapping DeepEval, Ragas and an OpenAI-Evals-compatible
format behind one unified interface. **`faithfulness` is backed by the
real `deepeval` package** — see `core/deepeval_adapter.py`, which wraps
`deepeval.metrics.FaithfulnessMetric` behind the same `EvalMetric`
protocol defined here; `resolve_metric()` in that module is the one
`Evaluator` actually calls, and it defers to `_REGISTRY` below for every
metric except `faithfulness`. An earlier version of this module assumed
DeepEval "pulls in heavy dependency trees (torch, transformer model
downloads)" and reimplemented faithfulness as a local heuristic instead —
that assumption was wrong (DeepEval installs in a few seconds with ~35
lightweight dependencies, no local models; verified, not assumed) and is
corrected here. `HeuristicFaithfulnessMetric` below is that original
term-overlap implementation, kept as the automatic fallback when the real
DeepEval call fails (network/parsing failure), and as what the LLD's own
"lightweight" characterisation actually applies to now: `coherence` and
`tool_trace_correctness`, which have no equivalent off-the-shelf DeepEval
metric worth wrapping, plus `financial_guidance_compliance` — ported
conceptually, not literally, from AgentEval, whose source isn't available
in this build environment. Ragas remains unintegrated; the same technique
proven here for DeepEval would apply equally to it if a Ragas-backed
metric becomes worth the effort. Any metric name covered by neither this
registry nor DeepEval falls back to an LLM Gateway LLM-as-judge call
(`core/ports.py`'s `LLMGatewayClient.judge`).
"""
from __future__ import annotations

import re
from typing import Any, Protocol

from evaluation_framework.core.ports import LLMGatewayClient
from evaluation_framework.core.similarity import cosine_similarity, tokenize


class EvalMetric(Protocol):
    async def compute(self, agent_output: str, reference_data: dict[str, Any], llm_gateway: LLMGatewayClient) -> float: ...


class HeuristicFaithfulnessMetric:
    """Term-overlap cosine similarity between the agent output and
    `reference_data["context"]` — the same lightweight approach Guardrails'
    Groundedness Checker uses for the same underlying question (is this text
    supported by this context?). No longer the primary `faithfulness`
    implementation — see this module's docstring — but kept as the
    fallback `DeepEvalFaithfulnessMetric` uses when the real DeepEval call
    fails."""

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
    "faithfulness": HeuristicFaithfulnessMetric(),  # overridden by deepeval_adapter.resolve_metric()
    "coherence": CoherenceMetric(),
    "tool_trace_correctness": ToolTraceCorrectnessMetric(),
    "financial_guidance_compliance": FinancialGuidanceComplianceMetric(),
}


def resolve_metric(metric_name: str) -> EvalMetric:
    """Callers wanting the real DeepEval-backed `faithfulness` metric should use
    `deepeval_adapter.resolve_metric()` instead — this module can't import that one
    itself (it would be a circular import: `deepeval_adapter` depends on
    `HeuristicFaithfulnessMetric` from here as its fallback)."""
    return _REGISTRY.get(metric_name, LLMJudgeMetric(metric_name))
