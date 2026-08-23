"""Classification Service (LLD §3.4): orchestrates the primary classifier,
compositional signal detection, and LLM fallback — this module's central
coordinator, same role as the orchestrators in Modules 1-4.
"""
from __future__ import annotations

import time

from intent_detection.config import ClassificationConfig
from intent_detection.core.compositional_decomposer import CompositionalDecomposer
from intent_detection.core.domain import (
    ClassificationLogRecord,
    ClassificationResult,
    NoActiveTaxonomyError,
    hash_input,
    new_id,
)
from intent_detection.core.llm_fallback import LLMFallbackHandler
from intent_detection.core.ports import IntentRepository
from intent_detection.core.primary_classifier import PrimaryClassifier
from intent_detection.telemetry.metrics import (
    intent_classification_duration_seconds,
    intent_classifications_total,
    intent_confidence_score,
)


class ClassificationService:
    def __init__(
        self,
        repository: IntentRepository,
        primary_classifier: PrimaryClassifier,
        decomposer: CompositionalDecomposer,
        fallback_handler: LLMFallbackHandler,
        config: ClassificationConfig,
    ) -> None:
        self.repository = repository
        self.primary_classifier = primary_classifier
        self.decomposer = decomposer
        self.fallback_handler = fallback_handler
        self.config = config

    async def classify(self, text: str, tenant_id: str, taxonomy_version: int | None = None) -> ClassificationResult:
        start = time.perf_counter()

        taxonomy = (
            await self.repository.get_taxonomy_by_version(tenant_id, taxonomy_version)
            if taxonomy_version is not None
            else await self.repository.get_active_taxonomy(tenant_id)
        )
        if taxonomy is None:
            raise NoActiveTaxonomyError(f"no active taxonomy for tenant '{tenant_id}'")

        scored = self.primary_classifier.classify(text, taxonomy.intents)
        top = scored[0] if scored else None
        multi_signal = self.config.multi_intent_detection_enabled and self.decomposer.has_multi_intent_signal(text)
        low_confidence = top is None or top.confidence < self.config.confidence_threshold

        fallback_used = low_confidence or multi_signal
        if fallback_used:
            intents = await self.fallback_handler.resolve(text, taxonomy, tenant_id)
            if not intents:  # LLM fallback returned nothing usable — fall back to the primary top-1
                intents = [top] if top else []
        else:
            intents = [top] if top else []

        await self.repository.create_classification_log(
            ClassificationLogRecord(
                id=new_id(),
                tenant_id=tenant_id,
                input_hash=hash_input(text),
                taxonomy_version=taxonomy.version,
                intents_detected=intents,
                fallback_used=fallback_used,
            )
        )

        intent_classifications_total.labels(tenant_id=tenant_id, fallback_used=str(fallback_used).lower()).inc()
        intent_classification_duration_seconds.labels(
            tenant_id=tenant_id, fallback_used=str(fallback_used).lower()
        ).observe(time.perf_counter() - start)
        if intents:
            intent_confidence_score.labels(tenant_id=tenant_id).observe(intents[0].confidence)

        return ClassificationResult(intents=intents, fallback_used=fallback_used, taxonomy_version=taxonomy.version)
