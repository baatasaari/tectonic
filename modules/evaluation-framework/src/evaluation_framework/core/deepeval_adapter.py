"""Real DeepEval integration (LLD §Level 1 "chosen stack": "wraps multiple
open source eval libraries behind one unified interface: DeepEval,
Ragas...").

This module genuinely uses the `deepeval` package's own metric classes
(`deepeval.metrics.FaithfulnessMetric`, etc.) rather than reimplementing
their scoring logic — verified against the real library, not assumed:
`deepeval` installs in a few seconds with ~35 lightweight dependencies
(no torch, no local model downloads; its LLM-as-judge calls go through a
`DeepEvalBaseLLM` subclass you provide). `DeepEvalLLMGatewayModel` is that
subclass — it routes every one of DeepEval's internal judge calls through
this module's own `LLMGatewayClient.complete()`, consistent with this
platform's rule that LLM Gateway is the only module permitted to call a
model provider directly. DeepEval's own prompt templates already embed
the schema/format instructions per call (truths extraction, claims
extraction, verdicts, score-reason), so the adapter itself stays
schema-agnostic: it forwards the rendered prompt as-is and returns raw
text, letting DeepEval's own lenient JSON extraction (`trimAndLoadJson`)
handle the rest — the same contract a real hosted LLM completion API
would satisfy.
"""
from __future__ import annotations

import os

# Must be set before the first `deepeval` import anywhere in the process — this disables
# DeepEval's own analytics/update-check network calls, which have no place in an
# offline-testable, self-contained platform module (and fail loudly through this build
# environment's egress proxy otherwise).
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from typing import Any

from deepeval.metrics import FaithfulnessMetric
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase

from evaluation_framework.core import metric_adapters
from evaluation_framework.core.metric_adapters import (
    EvalMetric,
    HeuristicFaithfulnessMetric,
)
from evaluation_framework.core.ports import LLMGatewayClient
from evaluation_framework.telemetry.logging import get_logger

logger = get_logger(component="deepeval_adapter")


class DeepEvalLLMGatewayModel(DeepEvalBaseLLM):
    """Adapts this module's `LLMGatewayClient` port to DeepEval's
    `DeepEvalBaseLLM` interface — every judge call DeepEval's metric
    classes make routes through here, and from here through LLM Gateway.
    """

    def __init__(self, llm_gateway: LLMGatewayClient) -> None:
        self._llm_gateway = llm_gateway
        super().__init__(model="llm-gateway")

    def load_model(self) -> DeepEvalLLMGatewayModel:
        return self

    def generate(self, prompt: str, schema: Any = None) -> str:
        raise NotImplementedError("DeepEvalLLMGatewayModel is async-only; use a_measure(), not measure().")

    async def a_generate(self, prompt: str, schema: Any = None) -> str:
        # `schema` is intentionally ignored: DeepEval's own prompt template already
        # embeds the exact JSON shape it wants (see this module's docstring), and its
        # `trimAndLoadJson` extraction is lenient about surrounding text — the same
        # contract as a real hosted completion API, not a structured-output API.
        return await self._llm_gateway.complete(prompt)

    def get_model_name(self) -> str:
        return "llm-gateway"


class DeepEvalFaithfulnessMetric:
    """`EvalMetric`-protocol adapter wrapping the real
    `deepeval.metrics.FaithfulnessMetric`. Falls back to the local
    term-overlap heuristic (`HeuristicFaithfulnessMetric`) if the DeepEval
    call fails — e.g. LLM Gateway unreachable, or the backing model
    returned unparseable JSON — the same "real call for the common case,
    documented fallback for the degraded case" pattern used elsewhere in
    this platform (Guardrails' ambiguous-jailbreak fallback,
    Observability's reasoning-narrative fallback), so an infrastructure
    hiccup degrades score quality rather than failing the whole eval run.
    """

    def __init__(self, *, threshold: float = 0.5) -> None:
        self._threshold = threshold
        self._fallback = HeuristicFaithfulnessMetric()

    async def compute(self, agent_output: str, reference_data: dict[str, Any], llm_gateway: LLMGatewayClient) -> float:
        context = reference_data.get("context", "")
        if not context:
            return 0.0

        model = DeepEvalLLMGatewayModel(llm_gateway)
        metric = FaithfulnessMetric(threshold=self._threshold, model=model, include_reason=False)
        test_case = LLMTestCase(input="", actual_output=agent_output, retrieval_context=[context])
        try:
            return await metric.a_measure(test_case, _show_indicator=False)
        except Exception as exc:
            logger.warning("deepeval_faithfulness_failed_using_fallback", error=str(exc))
            return await self._fallback.compute(agent_output, reference_data, llm_gateway)


_deepeval_faithfulness = DeepEvalFaithfulnessMetric()


def resolve_metric(metric_name: str) -> EvalMetric:
    """The entrypoint `Evaluator` actually calls — real DeepEval for
    `faithfulness`, `metric_adapters.resolve_metric()` (heuristics, then
    the LLM-as-judge fallback) for everything else."""
    if metric_name == "faithfulness":
        return _deepeval_faithfulness
    return metric_adapters.resolve_metric(metric_name)
