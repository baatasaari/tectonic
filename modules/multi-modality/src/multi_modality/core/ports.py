"""Abstract ports this module depends on: persistence, the per-modality
extractor protocol, and the real Guardrails peer client the groundedness
gate reads from.
"""
from __future__ import annotations

from typing import Any, Protocol

from multi_modality.core.domain import ExtractionRecord, Modality


class MultiModalityRepository(Protocol):
    async def create_extraction(self, record: ExtractionRecord) -> ExtractionRecord: ...

    async def get_extraction(self, extraction_id: str) -> ExtractionRecord | None: ...

    async def list_extractions(
        self, *, tenant_id: str | None = None, modality: Modality | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ExtractionRecord], int]: ...


class ModalityExtractor(Protocol):
    def extract(self, raw_content: str) -> str:
        """Normalizes `raw_content` for this modality into the common
        `extracted_content` shape. Synchronous and deterministic today
        (this LLD's own stand-in); a real deployment swaps this for an
        adapter calling a cloud ASR/vision/OCR provider, the same
        pluggable-port shape this platform already uses for its
        Tectonic-peer clients."""
        ...


class GuardrailsClient(Protocol):
    async def check_groundedness(self, *, tenant_id: str, text: str, context: str) -> dict[str, Any]:
        """Guardrails' own `POST /v1/guardrails/check` at `stage=output`,
        the identical endpoint and `groundedness_check` logic this
        platform already uses to catch ungrounded LLM output. Returns at
        least `{"decision": str, "violation_category": str | None}`."""
        ...
