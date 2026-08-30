"""In-memory fakes for unit tests."""
from __future__ import annotations

import ast
import json
import re
from typing import Any

from evaluation_framework.core.domain import (
    DomainMetricPackRecord,
    EvalRunRecord,
    GateResultRecord,
    MetricScoreRecord,
)
from evaluation_framework.core.similarity import tokenize


class InMemoryEvaluationFrameworkRepository:
    def __init__(self) -> None:
        self.eval_runs: dict[str, EvalRunRecord] = {}
        self.metric_scores: dict[str, MetricScoreRecord] = {}
        self.gate_results: dict[str, GateResultRecord] = {}
        self.domain_packs: dict[str, DomainMetricPackRecord] = {}

    async def create_eval_run(self, record: EvalRunRecord) -> EvalRunRecord:
        self.eval_runs[record.id] = record
        return record

    async def update_eval_run(self, record: EvalRunRecord) -> EvalRunRecord:
        self.eval_runs[record.id] = record
        return record

    async def get_eval_run(self, tenant_id: str, eval_run_id: str) -> EvalRunRecord | None:
        run = self.eval_runs.get(eval_run_id)
        if run is None or run.tenant_id != tenant_id:
            return None
        return run

    async def create_metric_score(self, record: MetricScoreRecord) -> MetricScoreRecord:
        self.metric_scores[record.id] = record
        return record

    async def list_metric_scores_for_run(self, eval_run_id: str) -> list[MetricScoreRecord]:
        return [s for s in self.metric_scores.values() if s.eval_run_id == eval_run_id]

    async def list_metric_scores_for_tenant(
        self, tenant_id: str, *, agent_ref: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[MetricScoreRecord], int]:
        results = [s for s in self.metric_scores.values() if s.tenant_id == tenant_id]
        if agent_ref is not None:
            results = [s for s in results if s.agent_ref == agent_ref]
        results = sorted(results, key=lambda s: s.created_at, reverse=True)
        return results[offset : offset + limit], len(results)

    async def list_eval_runs_for_agent_ref(
        self, tenant_id: str, agent_ref: str, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[EvalRunRecord], int]:
        results = [
            r for r in self.eval_runs.values() if r.tenant_id == tenant_id and r.agent_ref == agent_ref
        ]
        results = sorted(results, key=lambda r: r.started_at, reverse=True)
        return results[offset : offset + limit], len(results)

    async def create_gate_result(self, record: GateResultRecord) -> GateResultRecord:
        self.gate_results[record.id] = record
        return record

    async def create_domain_pack(self, record: DomainMetricPackRecord) -> DomainMetricPackRecord:
        self.domain_packs[record.id] = record
        return record

    async def list_domain_packs(self, tenant_id: str) -> list[DomainMetricPackRecord]:
        return [p for p in self.domain_packs.values() if p.tenant_id == tenant_id]


_DEEPEVAL_TRUTHS_MARKER = "please generate a comprehensive list of FACTUAL"
_DEEPEVAL_CLAIMS_MARKER = "please extract a comprehensive list of FACTUAL"
_DEEPEVAL_VERDICTS_MARKER = "generate a list of JSON objects to indicate whether EACH claim contradicts"
_DEEPEVAL_REASON_MARKER = "Given the faithfulness score, which is a 0-1 score"
_VERDICT_AGREEMENT_THRESHOLD = 0.5


def _claim_recall(claim_tokens, context_tokens) -> float:
    """Fraction of the claim's tokens that also appear in the context — directional
    (unlike cosine similarity), which is what "is this claim supported by this
    context" actually asks: a short claim fully contained in a long context should
    score high even though the context has plenty of tokens the claim doesn't."""
    total = sum(claim_tokens.values())
    if total == 0:
        return 1.0
    supported = sum(min(count, context_tokens.get(token, 0)) for token, count in claim_tokens.items())
    return supported / total


class StubLLMGatewayClient:
    def __init__(self, judged_score: float = 0.8) -> None:
        self.calls: list[dict] = []
        self.completion_calls: list[str] = []
        self.judged_score = judged_score

    async def judge(self, agent_output: str, metric_name: str, reference_data: dict[str, Any]) -> float:
        self.calls.append({"agent_output": agent_output, "metric_name": metric_name, "reference_data": reference_data})
        return self.judged_score

    async def complete(self, prompt: str) -> str:
        """Scripted responder for DeepEval's own prompt templates (see
        `core/deepeval_adapter.py`), so unit tests exercise the real
        `deepeval.metrics.FaithfulnessMetric` pipeline end to end without a network
        call. Verdicts are computed from real token-overlap recall of each claim
        against the embedded retrieval context — not a fixed canned answer — so an
        unfaithful claim genuinely scores differently from a faithful one, the same
        as it would against a real backing LLM."""
        self.completion_calls.append(prompt)

        if _DEEPEVAL_TRUTHS_MARKER in prompt:
            text = _extract_between(prompt, "Text:\n", "\n\nJSON:")
            return json.dumps({"truths": [text] if text else []})

        if _DEEPEVAL_CLAIMS_MARKER in prompt:
            text = _extract_between(prompt, "AI Output:\n", "\n\nJSON:")
            return json.dumps({"claims": [text] if text else []})

        if _DEEPEVAL_VERDICTS_MARKER in prompt:
            match = re.search(r"Retrieval Contexts:\n(.*?)\n\nClaims:\n(\[.*?\])\n\nJSON:", prompt, re.DOTALL)
            if not match:
                return json.dumps({"verdicts": []})
            context_text, claims = match.group(1), ast.literal_eval(match.group(2))
            context_tokens = tokenize(context_text)
            verdicts = []
            for claim in claims:
                if _claim_recall(tokenize(claim), context_tokens) >= _VERDICT_AGREEMENT_THRESHOLD:
                    verdicts.append({"verdict": "yes"})
                else:
                    verdicts.append({"verdict": "no", "reason": "not supported by the retrieval context"})
            return json.dumps({"verdicts": verdicts})

        if _DEEPEVAL_REASON_MARKER in prompt:
            return json.dumps({"reason": "Generated by the stub LLM Gateway for offline testing."})

        return json.dumps({})


def _extract_between(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start == -1:
        return ""
    start += len(start_marker)
    end = text.find(end_marker, start)
    if end == -1:
        return text[start:].strip()
    return text[start:end].strip()
