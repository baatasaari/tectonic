"""In-memory fakes for unit tests (LLD "Deployability and testability
contract")."""
from __future__ import annotations

from typing import Any

from multi_modality.core.domain import ExtractionRecord, Modality

_UNSET = object()


class InMemoryMultiModalityRepository:
    def __init__(self) -> None:
        self.extractions: dict[str, ExtractionRecord] = {}

    async def create_extraction(self, record: ExtractionRecord) -> ExtractionRecord:
        self.extractions[record.id] = record
        return record

    async def get_extraction(self, extraction_id: str) -> ExtractionRecord | None:
        return self.extractions.get(extraction_id)

    async def list_extractions(
        self, *, tenant_id: str | None = None, modality: Modality | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ExtractionRecord], int]:
        results = list(self.extractions.values())
        if tenant_id is not None:
            results = [e for e in results if e.tenant_id == tenant_id]
        if modality is not None:
            results = [e for e in results if e.modality == modality]
        results = sorted(results, key=lambda e: e.created_at)
        return results[offset:offset + limit], len(results)


class StubGuardrailsClient:
    def __init__(
        self, *, decision: str | object = _UNSET, violation_category: str | None = None,
        raise_error: bool = False,
    ) -> None:
        self.calls: list[dict] = []
        self._decision = "allow" if decision is _UNSET else decision
        self._violation_category = violation_category
        self._raise_error = raise_error

    async def check_groundedness(self, *, tenant_id: str, text: str, context: str) -> dict[str, Any]:
        self.calls.append({"tenant_id": tenant_id, "text": text, "context": context})
        if self._raise_error:
            raise RuntimeError("guardrails is down")
        return {"decision": self._decision, "violation_category": self._violation_category}


__all__ = ["InMemoryMultiModalityRepository", "StubGuardrailsClient"]
