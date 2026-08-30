"""Trace completeness (LLD §3 API surface `/trace-completeness`): the
fraction of spans present vs expected per known workflow shapes, used to
detect instrumentation gaps.
"""
from __future__ import annotations

from observability.core.domain import TraceCompletenessResult
from observability.core.ports import ObservabilityRepository


class TraceCompletenessCalculator:
    def __init__(self, repository: ObservabilityRepository, expected_spans: dict[str, list[str]]) -> None:
        self._repository = repository
        self._expected_spans = expected_spans

    async def compute(self, tenant_id: str) -> TraceCompletenessResult:
        traces = await self._repository.list_traces_for_tenant(tenant_id)
        known = [(trace_id, wt) for trace_id, wt in traces if wt and wt in self._expected_spans]

        if not known:
            # No trace tagged with a workflow_type this module has an expected shape for —
            # nothing to compare against, so there is no known incompleteness to report.
            return TraceCompletenessResult(
                tenant_id=tenant_id, completeness_ratio=1.0, traces_checked=len(traces), traces_with_known_shape=0,
            )

        ratios: list[float] = []
        for trace_id, workflow_type in known:
            expected_names = set(self._expected_spans[workflow_type])
            if not expected_names:
                continue
            spans = await self._repository.list_spans_for_trace(tenant_id, trace_id)
            observed_names = {s.name for s in spans}
            ratios.append(len(observed_names & expected_names) / len(expected_names))

        ratio = sum(ratios) / len(ratios) if ratios else 1.0
        return TraceCompletenessResult(
            tenant_id=tenant_id, completeness_ratio=ratio, traces_checked=len(traces), traces_with_known_shape=len(known),
        )
