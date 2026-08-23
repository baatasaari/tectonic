"""Abstract ports the assembly pipeline depends on: ontology/weights/log
persistence, LLM Gateway for summarisation, and the Evaluation Framework
feedback feed the Prioritisation Engine learns from.
"""
from __future__ import annotations

from typing import Protocol

from context_engineering.core.domain import (
    ContextAssemblyRecord,
    OntologyConfigRecord,
    PrioritisationWeightsRecord,
)


class ContextRepository(Protocol):
    async def create_ontology(self, record: OntologyConfigRecord) -> OntologyConfigRecord: ...

    async def get_active_ontology(self, tenant_id: str) -> OntologyConfigRecord | None: ...

    async def get_weights(self, tenant_id: str, task_type: str) -> PrioritisationWeightsRecord | None: ...

    async def upsert_weights(self, record: PrioritisationWeightsRecord) -> PrioritisationWeightsRecord: ...

    async def create_assembly_log(self, record: ContextAssemblyRecord) -> ContextAssemblyRecord: ...


class LLMGatewayClient(Protocol):
    async def summarise(self, *, content: str, target_tokens: int, tenant_id: str) -> str: ...


class EvaluationFeedbackClient(Protocol):
    async def get_feature_feedback(self, *, tenant_id: str, task_type: str) -> dict[str, float]:
        """Returns feature -> weight-delta signals scored by the
        Evaluation Framework from which context elements actually
        influenced correct answers historically."""
        ...
