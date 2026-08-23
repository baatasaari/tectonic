"""In-memory fakes for the ports in core/ports.py — the unit-test tier,
mirroring the other modules' core/fakes.py.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

from context_engineering.core.domain import (
    ContextAssemblyRecord,
    OntologyConfigRecord,
    PrioritisationWeightsRecord,
)


class InMemoryContextRepository:
    def __init__(self) -> None:
        self.ontologies: dict[str, OntologyConfigRecord] = {}
        self.weights: dict[tuple[str, str], PrioritisationWeightsRecord] = {}
        self.assembly_logs: list[ContextAssemblyRecord] = []

    async def create_ontology(self, record: OntologyConfigRecord) -> OntologyConfigRecord:
        self.ontologies[record.tenant_id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_active_ontology(self, tenant_id: str) -> OntologyConfigRecord | None:
        rec = self.ontologies.get(tenant_id)
        return copy.deepcopy(rec) if rec else None

    async def get_weights(self, tenant_id: str, task_type: str) -> PrioritisationWeightsRecord | None:
        rec = self.weights.get((tenant_id, task_type))
        return copy.deepcopy(rec) if rec else None

    async def upsert_weights(self, record: PrioritisationWeightsRecord) -> PrioritisationWeightsRecord:
        self.weights[(record.tenant_id, record.task_type)] = replace(record)
        return copy.deepcopy(record)

    async def create_assembly_log(self, record: ContextAssemblyRecord) -> ContextAssemblyRecord:
        self.assembly_logs.append(copy.deepcopy(record))
        return copy.deepcopy(record)


class StubLLMGatewayClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def summarise(self, *, content: str, target_tokens: int, tenant_id: str) -> str:
        self.calls.append({"content": content, "target_tokens": target_tokens, "tenant_id": tenant_id})
        words = content.split()
        keep = max(1, min(len(words), target_tokens))
        return " ".join(words[:keep])


class StubEvaluationFeedbackClient:
    def __init__(self) -> None:
        self.feedback: dict[str, float] = {}

    async def get_feature_feedback(self, *, tenant_id: str, task_type: str) -> dict[str, float]:
        return dict(self.feedback)
