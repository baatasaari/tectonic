"""Extraction Service (LLD §2 sub-components, §Level 3 "The groundedness
gate"): runs the right per-modality extractor, then -- only when a
`grounding_context` is supplied -- checks the extracted content's
groundedness against it through Guardrails' own real check endpoint.
Never fails the whole extraction over an unavailable Guardrails: that
degrades the verdict to `unavailable`, not the request.
"""
from __future__ import annotations

import time
from collections.abc import Awaitable, Mapping
from typing import Any, TypeVar

from multi_modality.core.domain import ExtractionRecord, GroundednessDecision, Modality, new_id
from multi_modality.core.ports import GuardrailsClient, MultiModalityRepository
from multi_modality.telemetry.logging import get_logger

logger = get_logger(component="extraction_service")

T = TypeVar("T")


class ExtractionService:
    def __init__(
        self, repository: MultiModalityRepository, guardrails: GuardrailsClient,
        extractors: Mapping[Modality, Any],
    ) -> None:
        self._repository = repository
        self._guardrails = guardrails
        self._extractors = extractors

    @staticmethod
    async def _safe_call(call: Awaitable[T], *, default: T) -> T:
        try:
            return await call
        except Exception as exc:
            logger.warning("groundedness_check_unavailable", error=str(exc))
            return default

    async def extract(
        self, *, tenant_id: str, modality: Modality, raw_content: str, grounding_context: str | None = None,
    ) -> ExtractionRecord:
        started = time.perf_counter()
        extractor = self._extractors[modality]
        extracted_content = extractor.extract(raw_content)

        groundedness_decision = GroundednessDecision.NOT_CHECKED
        violation_category = None
        if grounding_context is not None:
            result = await self._safe_call(
                self._guardrails.check_groundedness(
                    tenant_id=tenant_id, text=extracted_content, context=grounding_context,
                ),
                default=None,
            )
            if result is None:
                groundedness_decision = GroundednessDecision.UNAVAILABLE
            else:
                groundedness_decision = GroundednessDecision(result["decision"])
                violation_category = result.get("violation_category")

        latency_ms = (time.perf_counter() - started) * 1000

        record = ExtractionRecord(
            id=new_id(), tenant_id=tenant_id, modality=modality, raw_content=raw_content,
            extracted_content=extracted_content, grounding_context=grounding_context,
            groundedness_decision=groundedness_decision, groundedness_violation_category=violation_category,
            latency_ms=latency_ms,
        )
        return await self._repository.create_extraction(record)
